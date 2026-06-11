"""Integration tests for the API endpoints."""

import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app

client = TestClient(app)
VALID_KEY = "test-token-12345"


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success():
    response = client.post(
        "/skus",
        json={"sku": "TEST001", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST001"
    assert data["stock"] == 100


def test_create_sku_no_auth():
    response = client.post(
        "/skus",
        json={"sku": "TEST001", "initial_stock": 100}
    )
    assert response.status_code == 403


def test_create_sku_invalid_auth():
    response = client.post(
        "/skus",
        json={"sku": "TEST001", "initial_stock": 100},
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401


def test_adjust_stock_success():
    client.post(
        "/skus",
        json={"sku": "TEST002", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST002", "amount": 50},
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 150


def test_adjust_stock_no_auth():
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST002", "amount": 50}
    )
    assert response.status_code == 403


def test_create_reservation_happy_path():
    client.post(
        "/skus",
        json={"sku": "TEST003", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "TEST003", "quantity": 30, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST003"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"sku": "TEST004", "initial_stock": 50},
        headers={"X-API-Key": VALID_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "TEST004", "quantity": 100, "idempotency_key": "idem-2"},
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency():
    client.post(
        "/skus",
        json={"sku": "TEST005", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "TEST005", "quantity": 30, "idempotency_key": "idem-3"},
        headers={"X-API-Key": VALID_KEY}
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "TEST005", "quantity": 30, "idempotency_key": "idem-3"},
        headers={"X-API-Key": VALID_KEY}
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_create_reservation_no_auth():
    response = client.post(
        "/reservations",
        json={"sku": "TEST006", "quantity": 10, "idempotency_key": "idem-4"}
    )
    assert response.status_code == 403


def test_confirm_reservation_happy_path():
    client.post(
        "/skus",
        json={"sku": "TEST007", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST007", "quantity": 30, "idempotency_key": "idem-5"},
        headers={"X-API-Key": VALID_KEY}
    )
    res_id = res_response.json()["id"]
    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == res_id


def test_confirm_reservation_expired():
    client.post(
        "/skus",
        json={"sku": "TEST008", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST008", "quantity": 30, "idempotency_key": "idem-6"},
        headers={"X-API-Key": VALID_KEY}
    )
    res_id = res_response.json()["id"]
    from src.commerce_service.app import db
    from datetime import datetime, timezone, timedelta
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).replace(tzinfo=None)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time.isoformat(), res_id)
        )
        conn.commit()
    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_confirm_reservation_no_auth():
    response = client.post(
        "/reservations/1/confirm"
    )
    assert response.status_code == 403


def test_cancel_reservation_happy_path():
    client.post(
        "/skus",
        json={"sku": "TEST009", "initial_stock": 100},
        headers={"X-API-Key": VALID_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST009", "quantity": 30, "idempotency_key": "idem-7"},
        headers={"X-API-Key": VALID_KEY}
    )
    res_id = res_response.json()["id"]
    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": VALID_KEY}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_no_auth():
    response = client.post(
        "/reservations/1/cancel"
    )
    assert response.status_code == 403


def test_list_orders_empty():
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 0


def test_list_orders_pagination():
    client.post(
        "/skus",
        json={"sku": "TEST010", "initial_stock": 1000},
        headers={"X-API-Key": VALID_KEY}
    )
    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "TEST010", "quantity": 10, "idempotency_key": f"idem-{i}"},
            headers={"X-API-Key": VALID_KEY}
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY}
        )
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["total"] == 15
    response = client.get("/orders?page=2&size=10")
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2


def test_complete_workflow():
    client.post(
        "/skus",
        json={"sku": "WORKFLOW", "initial_stock": 500},
        headers={"X-API-Key": VALID_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "WORKFLOW", "quantity": 100, "idempotency_key": "workflow-1"},
        headers={"X-API-Key": VALID_KEY}
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]
    order_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_KEY}
    )
    assert order_response.status_code == 200
    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    assert orders_response.json()["total"] >= 1
