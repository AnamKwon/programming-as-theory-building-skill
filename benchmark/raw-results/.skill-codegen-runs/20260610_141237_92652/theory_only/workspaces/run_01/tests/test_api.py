import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


@pytest.fixture
def client(temp_db):
    from src.commerce_service import app as app_module
    app_module.repository = Repository(temp_db)
    app_module.service = CommerceService(app_module.repository)
    return TestClient(app)


VALID_TOKEN = "test-token"
INVALID_TOKEN = "invalid-token"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_no_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": INVALID_TOKEN}
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 25},
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 125


def test_adjust_stock_negative(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 70


def test_adjust_stock_no_token(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 10}
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key1"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"x-api-token": VALID_TOKEN}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 100,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert response1.status_code == 201
    assert response2.status_code == 201

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"x-api-token": VALID_TOKEN}
    )
    assert sku_response.json()["available_stock"] == 90


def test_create_reservation_no_token(client):
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        }
    )
    assert response.status_code == 401


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["order_id"] is not None


def test_confirm_reservation_expired(client):
    import sqlite3
    from datetime import datetime, timedelta

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    reservation_id = res_response.json()["id"]

    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    conn = sqlite3.connect("commerce.db")
    conn.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id)
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_confirm_reservation_wrong_status(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-token": VALID_TOKEN}
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 400


def test_confirm_reservation_no_token(client):
    response = client.post("/reservations/1/confirm")
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"x-api-token": VALID_TOKEN}
    )
    assert sku_response.json()["available_stock"] == 100


def test_cancel_reservation_no_token(client):
    response = client.post("/reservations/1/cancel")
    assert response.status_code == 401


def test_get_orders_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 5,
                "idempotency_key": f"key_{i}"
            },
            headers={"x-api-token": VALID_TOKEN}
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"x-api-token": VALID_TOKEN}
        )

    response = client.get(
        "/orders?page=1&size=10",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 10
    assert len(data["orders"]) == 5


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"x-api-token": VALID_TOKEN}
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 5,
                "idempotency_key": f"key_{i}"
            },
            headers={"x-api-token": VALID_TOKEN}
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"x-api-token": VALID_TOKEN}
        )

    page1 = client.get(
        "/orders?page=1&size=10",
        headers={"x-api-token": VALID_TOKEN}
    ).json()
    assert page1["total"] == 25
    assert len(page1["orders"]) == 10

    page2 = client.get(
        "/orders?page=2&size=10",
        headers={"x-api-token": VALID_TOKEN}
    ).json()
    assert len(page2["orders"]) == 10

    page3 = client.get(
        "/orders?page=3&size=10",
        headers={"x-api-token": VALID_TOKEN}
    ).json()
    assert len(page3["orders"]) == 5


def test_get_orders_no_token(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"x-api-token": VALID_TOKEN}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "key1"
        },
        headers={"x-api-token": VALID_TOKEN}
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["order_id"]

    orders_response = client.get(
        "/orders?page=1&size=10",
        headers={"x-api-token": VALID_TOKEN}
    )
    assert orders_response.status_code == 200
    orders = orders_response.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
    assert orders[0]["sku"] == "SKU001"
    assert orders[0]["quantity"] == 10
