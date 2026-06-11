"""Tests for API endpoints."""

import os
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import DATABASE_PATH, init_db


@pytest.fixture(autouse=True)
def clean_db():
    """Clean up database before each test."""
    db_path = Path(str(DATABASE_PATH))
    if db_path.exists():
        db_path.unlink()
    init_db()
    yield
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client():
    """Provide a test client."""
    return TestClient(app)


@pytest.fixture
def headers():
    """Provide valid API key headers."""
    return {"X-API-Key": "test-key-123"}


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_without_auth(client):
    """Test creating SKU without API key returns 401."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_with_invalid_auth(client):
    """Test creating SKU with invalid API key returns 401."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_sku_happy_path(client, headers):
    """Test creating SKU with valid auth."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_adjust_stock(client, headers):
    """Test adjusting stock."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 70


def test_create_reservation_insufficient_stock(client, headers):
    """Test reservation fails with insufficient stock."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 50}, headers=headers)

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_happy_path(client, headers):
    """Test creating a reservation."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key-1"


def test_idempotent_reservation_retry(client, headers):
    """Test idempotency - same key returns same reservation."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 20, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 20, "idempotency_key": "key-1"},
        headers=headers,
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["idempotency_key"] == data2["idempotency_key"]

    sku_response = client.get(
        "/orders?page=1&size=10",
        headers=headers,
    )
    orders = sku_response.json()
    assert orders["total"] == 0


def test_confirm_reservation_happy_path(client, headers):
    """Test confirming a reservation."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["confirmed_at"] is not None


def test_confirm_non_pending_reservation(client, headers):
    """Test confirming a non-PENDING reservation fails."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400


def test_reservation_expiration_on_confirm(client, headers):
    """Test that expired reservations cannot be confirmed."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res.json()["id"]

    from src.commerce_service.repository import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
        cursor.execute(
            "UPDATE reservation SET created_at = ? WHERE id = ?",
            (old_time, reservation_id),
        )
        conn.commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]

    updated_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert updated_res.status_code == 400


def test_cancel_reservation_happy_path(client, headers):
    """Test cancelling a reservation."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_non_pending_reservation(client, headers):
    """Test cancelling a non-PENDING reservation fails."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers=headers,
    )
    reservation_id = res.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 400


def test_get_orders_pagination(client, headers):
    """Test GET /orders pagination."""
    client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)

    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 5, "idempotency_key": f"key-{i}"},
            headers=headers,
        )
        reservation_id = res.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    response = client.get("/orders?page=1&size=10", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 15
    assert len(data["items"]) == 10

    response2 = client.get("/orders?page=2&size=10", headers=headers)
    data2 = response2.json()
    assert data2["page"] == 2
    assert len(data2["items"]) == 5


def test_unauthorized_mutation(client):
    """Test that missing API key returns 401 on mutation."""
    endpoints = [
        ("POST", "/skus", {"sku": "SKU001", "initial_stock": 100}),
        ("POST", "/stock/adjust", {"sku": "SKU001", "amount": 10}),
        ("POST", "/reservations", {"sku": "SKU001", "quantity": 10, "idempotency_key": "key"}),
    ]

    for method, path, body in endpoints:
        if method == "POST":
            response = client.post(path, json=body)
            assert response.status_code == 401
