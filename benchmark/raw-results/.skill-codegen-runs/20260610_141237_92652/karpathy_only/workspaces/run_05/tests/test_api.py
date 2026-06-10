import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from commerce_service import init_db
from commerce_service.app import app

VALID_TOKEN = "test-api-key-12345"

@pytest.fixture(autouse=True)
def setup_db():
    with patch.dict(os.environ, {"DB_PATH": ":memory:"}):
        init_db()
        yield

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"
    assert response.json()["stock"] == 100

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
        headers={"X-API-Token": "invalid-token"}
    )
    assert response.status_code == 401

def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 150

def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Token": VALID_TOKEN}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]

def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"

def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )

    assert res1.json()["id"] == res2.json()["id"]
    assert res1.json()["created_at"] == res2.json()["created_at"]

def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == res_id
    assert data["id"] is not None

def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

def test_expired_reservation(client):
    from unittest.mock import patch
    import time

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    res_id = res.json()["id"]
    created_at = res.json()["created_at"]

    with patch('commerce_service.service.time.time') as mock_time:
        mock_time.return_value = created_at + 301

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": VALID_TOKEN}
        )
        assert response.status_code == 400
        assert "Reservation expired" in response.json()["detail"]

def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Token": VALID_TOKEN}
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
            headers={"X-API-Token": VALID_TOKEN}
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": VALID_TOKEN}
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 2

    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["page"] == 3

def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU-ABC", "initial_stock": 500},
        headers={"X-API-Token": VALID_TOKEN}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-ABC", "quantity": 100, "idempotency_key": "workflow1"},
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert res.status_code == 201
    res_id = res.json()["id"]

    confirm = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN}
    )
    assert confirm.status_code == 200
    order_id = confirm.json()["id"]

    orders = client.get("/orders?page=1&size=10")
    assert orders.status_code == 200
    order_list = orders.json()
    assert order_list["total"] >= 1
    assert any(o["id"] == order_id for o in order_list["orders"])
