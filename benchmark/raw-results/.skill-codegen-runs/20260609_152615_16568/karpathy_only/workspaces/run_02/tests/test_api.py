import pytest
import os
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import init_db, DB_PATH

client = TestClient(app)
API_KEY = "test-key-change-in-production"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def setup_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku():
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "stock": 100},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["sku_id"] == "SKU001"
    assert response.json()["stock"] == 100


def test_create_sku_unauthorized():
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_wrong_key():
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    response = client.patch("/skus/SKU001/stock", json={"delta": 10}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["stock"] == 110


def test_create_reservation():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["quantity"] == 50


def test_create_reservation_insufficient_stock():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 101, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    response1 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_empty():
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_orders_pagination():
    client.post("/skus", json={"sku_id": "SKU001", "stock": 1000}, headers=HEADERS)

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers=HEADERS,
        )
        res_id = res_response.json()["reservation_id"]
        client.post(f"/reservations/{res_id}/confirm", json={}, headers=HEADERS)

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10
    assert data["limit"] == 10
    assert data["offset"] == 0

    response = client.get("/orders?limit=10&offset=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_reservation_expires():
    import sqlite3
    from datetime import datetime, timedelta

    client.post("/skus", json={"sku_id": "SKU001", "stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["reservation_id"]

    expires_at = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    conn = sqlite3.connect("commerce.db")
    c = conn.cursor()
    c.execute("UPDATE reservations SET expires_at = ? WHERE reservation_id = ?", (expires_at, reservation_id))
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 410
    assert "expired" in response.json()["detail"]


def test_unauthorized_mutations():
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "stock": 100},
    )
    assert response.status_code == 403

    response = client.patch("/skus/SKU001/stock", json={"delta": 10})
    assert response.status_code == 403

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
    )
    assert response.status_code == 403
