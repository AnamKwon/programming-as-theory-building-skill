import pytest
import tempfile
import os
import json
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository, get_db_connection, init_db


@pytest.fixture(autouse=True)
def setup_test_db():
    global DB_PATH
    original_db = None
    try:
        from src.commerce_service import repository
        original_db = repository.DB_PATH
        test_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        test_db.close()
        repository.DB_PATH = test_db.name
        init_db()
        yield
    finally:
        if original_db:
            from src.commerce_service import repository
            repository.DB_PATH = original_db
        if test_db:
            try:
                os.unlink(test_db.name)
            except:
                pass


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_without_token(client):
    response = client.post("/skus", json={"sku": "SKU123", "initial_stock": 100})
    assert response.status_code == 401


def test_create_sku_with_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU123", "initial_stock": 100},
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401


def test_create_sku_with_valid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU123", "initial_stock": 100},
        headers={"X-API-Key": "test-secret-token-12345"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU123"
    assert data["initial_stock"] == 100


def test_create_duplicate_sku(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)
    response = client.post("/skus", json={"sku": "SKU123", "initial_stock": 50}, headers=headers)
    assert response.status_code == 400


def test_adjust_stock_success(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU123", "amount": 50},
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU123"
    assert data["available_stock"] == 150


def test_adjust_stock_negative(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU123", "amount": -30},
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70


def test_adjust_stock_sku_not_found(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 50},
        headers=headers
    )
    assert response.status_code == 400


def test_create_reservation_insufficient_stock(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 50}, headers=headers)

    response = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 100, "idempotency_key": "key1"},
        headers=headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_success(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU123"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key1"
    assert "id" in data
    assert "created_at" in data


def test_create_reservation_idempotent(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    assert response1.status_code == 201
    first_id = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    assert response2.status_code == 201
    second_id = response2.json()["id"]
    assert first_id == second_id

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU123", "amount": 0},
        headers=headers
    )
    assert response.json()["available_stock"] == 50


def test_happy_path_workflow(client):
    headers = {"X-API-Key": "test-secret-token-12345"}

    client.post("/skus", json={"sku": "WIDGET", "initial_stock": 100}, headers=headers)

    res1 = client.post(
        "/reservations",
        json={"sku": "WIDGET", "quantity": 30, "idempotency_key": "order1"},
        headers=headers
    )
    assert res1.status_code == 201
    reservation_id = res1.json()["id"]

    res2 = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "CONFIRMED"

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert orders["total"] == 1
    assert orders["orders"][0]["sku"] == "WIDGET"


def test_confirm_reservation_expired(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    reservation_id = res1.json()["id"]

    from src.commerce_service.repository import get_db_connection
    from datetime import datetime, timedelta

    with get_db_connection() as conn:
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=400)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation_id)
        )
        conn.commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()

    from src.commerce_service.repository import Repository
    repo = Repository()
    stock = repo.get_sku_stock("SKU123")
    assert stock == 100


def test_confirm_reservation_not_pending(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    reservation_id = res1.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    response = client.post(f"/reservations/{reservation_id}/confirm", headers=headers)
    assert response.status_code == 400


def test_cancel_reservation_success(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 100}, headers=headers)

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU123", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    reservation_id = res1.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    from src.commerce_service.repository import Repository
    repo = Repository()
    stock = repo.get_sku_stock("SKU123")
    assert stock == 100


def test_get_orders_pagination(client):
    headers = {"X-API-Key": "test-secret-token-12345"}
    client.post("/skus", json={"sku": "SKU123", "initial_stock": 1000}, headers=headers)

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU123", "quantity": 10, "idempotency_key": f"key{i}"},
            headers=headers
        )
        res_id = res.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers=headers)

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["page"] == 1
    assert data1["size"] == 10
    assert data1["total"] == 25

    response2 = client.get("/orders?page=2&size=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 10
    assert data2["page"] == 2

    response3 = client.get("/orders?page=3&size=10")
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["orders"]) == 5
    assert data3["page"] == 3
