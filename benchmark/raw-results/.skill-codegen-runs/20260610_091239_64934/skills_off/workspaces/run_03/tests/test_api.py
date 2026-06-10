import pytest
import tempfile
import os
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr("commerce_service.app.db", temp_db)
    monkeypatch.setattr("commerce_service.app.service", CommerceService(temp_db))
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
    )
    assert response.status_code == 403
    assert "Missing API key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": "sk-test-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "SKU001"
    assert data["name"] == "Product 1"
    assert data["current_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_duplicate_code(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 2", "initial_stock": 50},
        headers=headers,
    )
    assert response.status_code == 409


def test_adjust_stock_unauthorized(client):
    response = client.post("/stock/1/adjust", json={"quantity": 50})
    assert response.status_code == 403


def test_adjust_stock_not_found(client):
    response = client.post(
        "/stock/999/adjust",
        json={"quantity": 50},
        headers={"X-API-Key": "sk-test-key-12345"},
    )
    assert response.status_code == 404


def test_adjust_stock_success(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 50},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["current_stock"] == 150


def test_create_reservation_insufficient_stock(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 10},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 20, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_success(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
    assert data["status"] == "pending"
    assert data["idempotency_key"] == "key-1"


def test_create_reservation_idempotency(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response1.status_code == 201
    reservation_id_1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response2.status_code == 201
    assert response2.json()["id"] == reservation_id_1


def test_confirm_reservation_success(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Key": "sk-test-key-12345"},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["offset"] == 0


def test_list_orders_pagination(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers=headers,
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers,
        )

    response = client.get("/orders?offset=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["offset"] == 0
    assert data["limit"] == 2


def test_get_order_not_found(client):
    response = client.get("/orders/999")
    assert response.status_code == 404


def test_get_order_success(client):
    headers = {"X-API-Key": "sk-test-key-12345"}
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )

    orders_response = client.get("/orders")
    order_id = orders_response.json()["items"][0]["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
