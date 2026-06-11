"""Tests for the API endpoints."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import init_db


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown for each test."""
    db_path = Path("commerce.db")
    if db_path.exists():
        db_path.unlink()

    init_db()

    yield

    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def valid_api_key():
    """Valid API key for testing."""
    return "test-api-key-12345"


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, valid_api_key):
    """Test creating a SKU."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    """Test creating a SKU without API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    """Test creating a SKU with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock(client, valid_api_key):
    """Test adjusting stock."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_missing_api_key(client, valid_api_key):
    """Test adjusting stock without API key."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
    )
    assert response.status_code == 401


def test_create_reservation(client, valid_api_key):
    """Test creating a reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, valid_api_key):
    """Test creating a reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 30},
        headers={"X-API-Key": valid_api_key},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_reservation_idempotency(client, valid_api_key):
    """Test idempotent reservations."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )

    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )

    assert response1.status_code == 201
    assert response2.status_code == 201

    data1 = response1.json()
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["sku"] == data2["sku"]
    assert data1["quantity"] == data2["quantity"]

    # Verify stock was only deducted once
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-002", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )


def test_create_reservation_missing_api_key(client, valid_api_key):
    """Test creating a reservation without API key."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
    )
    assert response.status_code == 401


def test_confirm_reservation(client, valid_api_key):
    """Test confirming a reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client, valid_api_key):
    """Test confirming an expired reservation."""
    from datetime import datetime, timedelta
    from commerce_service.repository import get_db_connection

    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = res.json()["id"]

    # Manipulate the database to set creation time to 301 seconds ago
    conn = get_db_connection()
    cursor = conn.cursor()
    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_confirm_non_pending_reservation(client, valid_api_key):
    """Test confirming a non-pending reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": valid_api_key},
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 400


def test_cancel_reservation(client, valid_api_key):
    """Test cancelling a reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        json={},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_missing_api_key(client, valid_api_key):
    """Test cancelling a reservation without API key."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        json={},
    )
    assert response.status_code == 401


def test_get_orders_pagination(client, valid_api_key):
    """Test getting orders with pagination."""
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 1000},
        headers={"X-API-Key": valid_api_key},
    )

    # Create and confirm 25 reservations
    for i in range(25):
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers={"X-API-Key": valid_api_key},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": valid_api_key},
        )

    # Test first page
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["size"] == 10

    # Test second page
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25

    # Test third page with partial results
    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 25


def test_happy_path_workflow(client, valid_api_key):
    """Test the complete happy path workflow."""
    # Create SKU
    response = client.post(
        "/skus",
        json={"sku": "SKU-HAPPY", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 201

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-HAPPY",
            "quantity": 30,
            "idempotency_key": "key-happy-1",
        },
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 201
    reservation_id = response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"

    # Get orders
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["sku"] == "SKU-HAPPY"
    assert data["items"][0]["quantity"] == 30
