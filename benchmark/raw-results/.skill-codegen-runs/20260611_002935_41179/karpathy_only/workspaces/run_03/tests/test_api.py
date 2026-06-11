import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from commerce_service.app import app, db, service
from commerce_service.repository import Database


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    os.environ["DATABASE_PATH"] = path
    temp_db_instance = Database(path)

    app.dependency_overrides[db.__class__] = lambda: temp_db_instance

    yield temp_db_instance

    try:
        os.remove(path)
    except:
        pass
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]


@pytest.fixture
def client(temp_db):
    return TestClient(app)


@pytest.fixture
def headers():
    return {"X-API-Key": "test-key-123"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, headers, temp_db):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=headers
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU-001"
    assert temp_db.get_sku_stock("SKU-001") == 100


def test_create_sku_missing_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_adjust_stock(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 150


def test_adjust_stock_negative(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -30},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 70


def test_happy_path_workflow(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-001"
        },
        headers=headers
    )
    assert res_response.status_code == 201
    reservation = res_response.json()
    assert reservation["status"] == "PENDING"
    assert reservation["quantity"] == 10
    assert temp_db.get_sku_stock("SKU-001") == 90

    conf_response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=headers
    )
    assert conf_response.status_code == 200
    order = conf_response.json()
    assert order["reservation_id"] == reservation["id"]

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert len(orders_data["items"]) == 1
    assert orders_data["items"][0]["reservation_id"] == reservation["id"]


def test_insufficient_stock(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 50)
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 100,
            "idempotency_key": "idem-002"
        },
        headers=headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"
    assert temp_db.get_sku_stock("SKU-001") == 50


def test_idempotent_reservation(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)

    first_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-003"
        },
        headers=headers
    )
    assert first_response.status_code == 201
    first_reservation = first_response.json()
    first_stock = temp_db.get_sku_stock("SKU-001")

    second_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-003"
        },
        headers=headers
    )
    assert second_response.status_code == 201
    second_reservation = second_response.json()

    assert first_reservation["id"] == second_reservation["id"]
    assert first_reservation["idempotency_key"] == second_reservation["idempotency_key"]
    assert temp_db.get_sku_stock("SKU-001") == first_stock


def test_expired_reservation(client, headers, temp_db):
    import time
    temp_db.create_sku("SKU-001", 100)

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-004"
        },
        headers=headers
    )
    assert res_response.status_code == 201
    reservation = res_response.json()
    assert temp_db.get_sku_stock("SKU-001") == 90

    time.sleep(301)

    conf_response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=headers
    )
    assert conf_response.status_code == 400
    assert "expired" in conf_response.json()["detail"].lower()

    updated_res = temp_db.get_reservation(reservation["id"])
    assert updated_res["status"] == "EXPIRED"
    assert temp_db.get_sku_stock("SKU-001") == 100


def test_confirm_non_pending_reservation(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-005"
        },
        headers=headers
    )
    reservation = res_response.json()

    conf_response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=headers
    )
    assert conf_response.status_code == 200

    conf_response2 = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=headers
    )
    assert conf_response2.status_code == 400
    assert "status" in conf_response2.json()["detail"]


def test_cancel_reservation(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-006"
        },
        headers=headers
    )
    reservation = res_response.json()
    assert temp_db.get_sku_stock("SKU-001") == 90

    cancel_response = client.post(
        f"/reservations/{reservation['id']}/cancel",
        headers=headers
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"
    assert temp_db.get_sku_stock("SKU-001") == 100


def test_cancel_non_pending_reservation(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 100)

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idem-007"
        },
        headers=headers
    )
    reservation = res_response.json()

    client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=headers
    )

    cancel_response = client.post(
        f"/reservations/{reservation['id']}/cancel",
        headers=headers
    )
    assert cancel_response.status_code == 400
    assert "status" in cancel_response.json()["detail"]


def test_orders_pagination(client, headers, temp_db):
    temp_db.create_sku("SKU-001", 1000)

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idem-pag-{i}"
            },
            headers=headers
        )
        reservation = res_response.json()
        client.post(
            f"/reservations/{reservation['id']}/confirm",
            headers=headers
        )

    page1 = client.get("/orders?page=1&size=10")
    assert page1.status_code == 200
    assert page1.json()["page"] == 1
    assert page1.json()["size"] == 10
    assert len(page1.json()["items"]) == 10
    assert page1.json()["total"] == 25

    page2 = client.get("/orders?page=2&size=10")
    assert page2.status_code == 200
    assert page2.json()["page"] == 2
    assert len(page2.json()["items"]) == 10

    page3 = client.get("/orders?page=3&size=10")
    assert page3.status_code == 200
    assert len(page3.json()["items"]) == 5
