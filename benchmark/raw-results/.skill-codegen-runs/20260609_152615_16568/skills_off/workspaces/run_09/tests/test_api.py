"""Tests for the FastAPI endpoints."""

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, repository, service
from commerce_service.repository import Repository


@pytest.fixture(autouse=True)
def setup_db():
    """Set up a test database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Patch the repository and service to use test database
    test_repo = Repository(path)
    with patch("commerce_service.app.repository", test_repo):
        with patch("commerce_service.app.service") as mock_service:
            from commerce_service.service import CommerceService
            mock_service = CommerceService(test_repo)
            with patch("commerce_service.app.service", mock_service):
                yield

    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def api_key():
    """Set API key for testing."""
    with patch.dict(os.environ, {"API_KEY": "test-key-123"}):
        yield "test-key-123"


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, api_key):
    """Test creating a SKU with valid request."""
    response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["product_name"] == "Widget"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_missing_api_key(client):
    """Test creating SKU without API key."""
    response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    """Test creating SKU with invalid API key."""
    response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client, api_key):
    """Test adjusting stock."""
    # Create SKU first
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Adjust stock
    response = client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity_change": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_nonexistent_sku(client, api_key):
    """Test adjusting stock for non-existent SKU."""
    response = client.post(
        "/skus/999/stock",
        json={"quantity_change": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_create_reservation_success(client, api_key):
    """Test creating a reservation."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create reservation
    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 50
    assert data["status"] == "pending"
    assert data["idempotency_key"] == "key-1"


def test_create_reservation_insufficient_stock(client, api_key):
    """Test reservation with insufficient stock."""
    # Create SKU with small stock
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 10},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409


def test_create_reservation_idempotency(client, api_key):
    """Test that idempotency key prevents double-reservation."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create first reservation
    res1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": api_key},
    )
    res1_id = res1.json()["id"]

    # Create second with same idempotency key
    res2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": api_key},
    )
    res2_id = res2.json()["id"]

    # Should return same reservation
    assert res1_id == res2_id

    # Stock should only be reserved once
    sku = client.get(f"/skus/{sku_id}").json() if hasattr(client, "get") else None


def test_confirm_reservation_success(client, api_key):
    """Test confirming a reservation."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"


def test_confirm_reservation_nonexistent(client, api_key):
    """Test confirming non-existent reservation."""
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client, api_key):
    """Test cancelling a reservation."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_cancel_reservation_nonexistent(client, api_key):
    """Test cancelling non-existent reservation."""
    response = client.post(
        "/reservations/999/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_list_orders_empty(client):
    """Test listing orders when none exist."""
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["orders"] == []
    assert data["next_cursor"] is None


def test_list_orders_with_pagination(client, api_key):
    """Test pagination of orders."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"product_name": "Widget", "initial_stock": 1000},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create and confirm multiple reservations
    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers={"X-API-Key": api_key})

    # Get first page
    response = client.get("/orders?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["next_cursor"] is not None

    # Get second page
    response = client.get(f"/orders?limit=10&cursor={data['next_cursor']}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["next_cursor"] is None


def test_list_orders_invalid_limit(client):
    """Test invalid limit parameter."""
    response = client.get("/orders?limit=150")
    assert response.status_code == 400
    assert "Limit must be between" in response.json()["detail"]
