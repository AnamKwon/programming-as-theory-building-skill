import pytest
import os
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import sqlite3

os.environ["DATABASE_FILE"] = "commerce_test_api.db"

from src.commerce_service.app import app
from src.commerce_service.repository import init_db, get_db_connection

DATABASE_FILE = "commerce_test_api.db"


@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
    init_db()
    yield
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)


@pytest.fixture
def client():
    return TestClient(app)


VALID_API_KEY = "test-api-key"
HEADERS = {"X-API-Key": VALID_API_KEY}
INVALID_HEADERS = {"X-API-Key": "invalid-key"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_no_auth():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_create_sku_missing_auth(client):
    response = client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100})
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=INVALID_HEADERS
    )
    assert response.status_code == 401


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 150, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_idempotent_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    assert response2.status_code == 200
    data2 = response2.json()

    assert data1["id"] == data2["id"]

    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 0},
        headers=HEADERS
    )


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders", headers=HEADERS)
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert len(orders_data["orders"]) == 1


def test_confirm_expired_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    reservation_id = res_response.json()["id"]

    conn = get_db_connection()
    cursor = conn.cursor()
    old_time = (datetime.utcnow() - timedelta(seconds=350)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id)
    )
    conn.commit()
    conn.close()

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS
    )
    assert confirm_response.status_code == 400
    assert "expired" in confirm_response.json()["detail"].lower()


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=HEADERS
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers=HEADERS
    )
    reservation_id = res_response.json()["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=HEADERS
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "PENDING"


def test_get_orders_paginated(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 1000},
        headers=HEADERS
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers=HEADERS
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=HEADERS
        )

    response1 = client.get("/orders?page=1&size=10", headers=HEADERS)
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["page"] == 1
    assert data1["total"] == 25

    response2 = client.get("/orders?page=2&size=10", headers=HEADERS)
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 10
    assert data2["page"] == 2

    response3 = client.get("/orders?page=3&size=10", headers=HEADERS)
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["orders"]) == 5
    assert data3["page"] == 3


def test_unauthorized_mutation_blocks(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50}
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"}
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/confirm"
    )
    assert response.status_code == 401

    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_workflow(client):
    sku_response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 500},
        headers=HEADERS
    )
    assert sku_response.status_code == 201

    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 100, "idempotency_key": "order-123"},
        headers=HEADERS
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders?page=1&size=10", headers=HEADERS)
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert orders_data["orders"][0]["sku"] == "WIDGET-001"
    assert orders_data["orders"][0]["quantity"] == 100
