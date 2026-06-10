import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, get_repository, get_service
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from datetime import datetime, timedelta


@pytest.fixture
def test_db():
    return Repository(":memory:")


@pytest.fixture
def test_service(test_db):
    return CommerceService(test_db)


@pytest.fixture
def client(test_db, test_service):
    app.dependency_overrides[get_repository] = lambda: test_db
    app.dependency_overrides[get_service] = lambda: test_service
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert "id" in data


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 30},
        headers={"X-API-Key": "secret-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "secret-key"},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "secret-key"},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1 == data2

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 0},
        headers={"X-API-Key": "secret-key"},
    )
    assert sku_response.json()["available_stock"] == 50


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "secret-key"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"]
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_unauthorized(client, test_service):
    test_service.create_sku("SKU-001", 100)
    reservation = test_service.create_reservation("SKU-001", 50, "key-1")

    response = client.post(f"/reservations/{reservation['id']}/confirm")
    assert response.status_code == 401


def test_confirm_reservation_not_pending(client, test_service):
    test_service.create_sku("SKU-001", 100)
    reservation = test_service.create_reservation("SKU-001", 50, "key-1")
    test_service.confirm_reservation(reservation["id"])

    response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]


def test_confirm_reservation_expired(client, test_service):
    test_service.create_sku("SKU-001", 100)
    reservation = test_service.create_reservation("SKU-001", 50, "key-1")

    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    conn = test_service.repo._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation["id"]),
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "secret-key"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["restored_quantity"] == 50


def test_cancel_reservation_not_pending(client, test_service):
    test_service.create_sku("SKU-001", 100)
    reservation = test_service.create_reservation("SKU-001", 50, "key-1")
    test_service.confirm_reservation(reservation["id"])

    response = client.post(
        f"/reservations/{reservation['id']}/cancel",
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]


def test_get_orders_unauthorized(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "secret-key"},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 1, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "secret-key"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "secret-key"},
        )

    response = client.get("/orders?page=1&size=10", headers={"X-API-Key": "secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25

    response = client.get("/orders?page=2&size=10", headers={"X-API-Key": "secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 2

    response = client.get("/orders?page=3&size=10", headers={"X-API-Key": "secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5


def test_full_workflow(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-123", "initial_stock": 50},
        headers={"X-API-Key": "secret-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-123", "quantity": 30, "idempotency_key": "order-001"},
        headers={"X-API-Key": "secret-key"},
    )
    assert res_response.status_code == 201
    reservation = res_response.json()
    assert reservation["status"] == "PENDING"

    confirm_response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers={"X-API-Key": "secret-key"},
    )
    assert confirm_response.status_code == 200
    order = confirm_response.json()
    assert order["reservation_id"] == reservation["id"]

    orders_response = client.get("/orders", headers={"X-API-Key": "secret-key"})
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert orders_data["orders"][0]["id"] == order["id"]
