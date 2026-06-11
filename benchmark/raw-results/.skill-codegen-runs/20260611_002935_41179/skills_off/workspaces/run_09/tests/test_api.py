"""Tests for the API endpoints."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import init_db, DATABASE_PATH
import commerce_service.security as security

# Use test API token
security.API_TOKEN = "test-token"

client = TestClient(app)

VALID_TOKEN = "test-token"
INVALID_TOKEN = "invalid-token"


@pytest.fixture(autouse=True)
def setup_test_db():
    """Set up test database for each test."""
    if Path(DATABASE_PATH).exists():
        os.remove(DATABASE_PATH)
    init_db()
    yield
    if Path(DATABASE_PATH).exists():
        os.remove(DATABASE_PATH)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success():
    """Test creating a SKU."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 201
    assert response.json() == {"sku": "SKU-001", "stock": 100}


def test_create_sku_unauthorized():
    """Test creating a SKU without valid token."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-002", "initial_stock": 100},
        headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
    )
    assert response.status_code == 401


def test_create_sku_no_token():
    """Test creating a SKU without token."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-003", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_adjust_stock():
    """Test adjusting stock."""
    client.post(
        "/skus",
        json={"sku": "SKU-004", "initial_stock": 50},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-004", "amount": 25},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 75


def test_reserve_stock_success():
    """Test successful stock reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-005", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-005", "quantity": 30, "idempotency_key": "key-1"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-005"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"
    assert "id" in data
    assert "created_at" in data


def test_reserve_stock_insufficient():
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "SKU-006", "initial_stock": 10},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-006", "quantity": 20, "idempotency_key": "key-2"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_reserve_stock_idempotency():
    """Test idempotent reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-007", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-007", "quantity": 30, "idempotency_key": "key-3"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-007", "quantity": 30, "idempotency_key": "key-3"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["created_at"] == data2["created_at"]


def test_confirm_reservation_success():
    """Test successful reservation confirmation."""
    client.post(
        "/skus",
        json={"sku": "SKU-008", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-008", "quantity": 25, "idempotency_key": "key-4"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["reservation_id"] == reservation_id
    assert "order_id" in data


def test_confirm_reservation_unauthorized():
    """Test confirming reservation without valid token."""
    client.post(
        "/skus",
        json={"sku": "SKU-009", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-009", "quantity": 25, "idempotency_key": "key-5"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
    )
    assert response.status_code == 401


def test_confirm_reservation_expired():
    """Test confirming an expired reservation."""
    from datetime import datetime, timedelta
    from commerce_service.repository import get_connection

    client.post(
        "/skus",
        json={"sku": "SKU-010", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-010", "quantity": 30, "idempotency_key": "key-6"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    reservation_id = res_response.json()["id"]

    old_timestamp = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_timestamp, reservation_id),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_cancel_reservation_success():
    """Test successful reservation cancellation."""
    client.post(
        "/skus",
        json={"sku": "SKU-011", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-011", "quantity": 35, "idempotency_key": "key-7"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["stock_restored"] == 35


def test_get_orders_success():
    """Test getting orders with pagination."""
    client.post(
        "/skus",
        json={"sku": "SKU-012", "initial_stock": 1000},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-012", "quantity": 10, "idempotency_key": f"key-order-{i}"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

    response = client.get(
        "/orders?page=1&size=10",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25


def test_get_orders_pagination_offset():
    """Test pagination offset behavior."""
    client.post(
        "/skus",
        json={"sku": "SKU-013", "initial_stock": 1000},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-013", "quantity": 10, "idempotency_key": f"key-offset-{i}"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

    page1 = client.get(
        "/orders?page=1&size=10",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    ).json()
    page2 = client.get(
        "/orders?page=2&size=10",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    ).json()
    page3 = client.get(
        "/orders?page=3&size=10",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    ).json()

    assert len(page1["orders"]) == 10
    assert len(page2["orders"]) == 10
    assert len(page3["orders"]) == 5

    ids_page1 = {o["id"] for o in page1["orders"]}
    ids_page2 = {o["id"] for o in page2["orders"]}
    ids_page3 = {o["id"] for o in page3["orders"]}

    assert len(ids_page1 & ids_page2) == 0
    assert len(ids_page2 & ids_page3) == 0
    assert len(ids_page1 & ids_page3) == 0


def test_full_workflow():
    """Test complete happy path workflow."""
    client.post(
        "/skus",
        json={"sku": "SKU-FINAL", "initial_stock": 1000},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-FINAL", "quantity": 100, "idempotency_key": "workflow-key"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert res_response.status_code == 201
    reservation = res_response.json()
    assert reservation["status"] == "PENDING"

    confirm_response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["status"] == "CONFIRMED"

    orders_response = client.get(
        "/orders?page=1&size=10",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert orders["total"] == 1
    assert orders["orders"][0]["reservation_id"] == reservation["id"]
