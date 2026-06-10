import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import Service
import sqlite3

client = TestClient(app)

AUTH_HEADER = {"Authorization": "Bearer test-token-secret"}
INVALID_AUTH_HEADER = {"Authorization": "Bearer invalid-token"}
MISSING_AUTH_HEADER = {}


@pytest.fixture(autouse=True)
def reset_db():
    import os
    if os.path.exists("commerce.db"):
        os.remove("commerce.db")
    yield
    if os.path.exists("commerce.db"):
        os.remove("commerce.db")


def test_health_no_auth():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_with_valid_auth():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_with_invalid_auth():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=INVALID_AUTH_HEADER
    )
    assert response.status_code == 401


def test_create_sku_with_missing_auth():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=MISSING_AUTH_HEADER
    )
    assert response.status_code == 401


def test_adjust_stock():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers=AUTH_HEADER
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_create_reservation_happy_path():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"
    assert "created_at" in data


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 20},
        headers=AUTH_HEADER
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    assert response1.status_code == 201
    data1 = response1.json()
    res_id1 = data1["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    assert response2.status_code == 201
    data2 = response2.json()
    res_id2 = data2["id"]

    assert res_id1 == res_id2
    assert data1 == data2

    sku_response = client.post(
        "/skus",
        json={"sku": "SKU002", "initial_stock": 100},
        headers=AUTH_HEADER
    )
    sku_data = sku_response.json()
    assert sku_data["available_stock"] == 70


def test_confirm_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=AUTH_HEADER
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_expired_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    res_id = res_response.json()["id"]

    old_created_at = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    with sqlite3.connect("commerce.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_created_at, res_id)
        )
        conn.commit()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=AUTH_HEADER
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"

    sku_response = client.post(
        "/skus",
        json={"sku": "SKU002", "initial_stock": 100},
        headers=AUTH_HEADER
    )
    sku_data = sku_response.json()
    assert sku_data["available_stock"] == 100


def test_confirm_non_pending_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/cancel",
        headers=AUTH_HEADER
    )

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=AUTH_HEADER
    )
    assert response.status_code == 400


def test_cancel_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=AUTH_HEADER
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idem-1"},
        headers=AUTH_HEADER
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=AUTH_HEADER
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    sku_response = client.post(
        "/skus",
        json={"sku": "SKU002", "initial_stock": 100},
        headers=AUTH_HEADER
    )
    sku_data = sku_response.json()
    assert sku_data["available_stock"] == 100


def test_get_orders_pagination():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers=AUTH_HEADER
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"idem-{i}"},
            headers=AUTH_HEADER
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers=AUTH_HEADER
        )

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["page"] == 1
    assert data1["size"] == 10

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

    response4 = client.get("/orders?page=4&size=10")
    assert response4.status_code == 200
    data4 = response4.json()
    assert len(data4["orders"]) == 0


def test_unauthorized_mutation_missing_token():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_unauthorized_mutation_invalid_token():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401
