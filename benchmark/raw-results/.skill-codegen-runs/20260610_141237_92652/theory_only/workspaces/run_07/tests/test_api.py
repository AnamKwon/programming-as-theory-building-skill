"""API endpoint integration tests."""

import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService

# Use in-memory database for tests
@pytest.fixture(scope="function")
def test_app():
    """Create test app with in-memory database."""
    from commerce_service import app as app_module

    # Replace the repository with in-memory one
    test_repo = Repository("sqlite:///:memory:")
    app_module.repository = test_repo
    app_module.service = CommerceService(test_repo)

    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def valid_headers():
    """Valid API key headers."""
    return {"X-API-Key": "test-key-123"}


@pytest.fixture
def invalid_headers():
    """Invalid API key headers."""
    return {"X-API-Key": "invalid-key"}


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, valid_headers):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert "Missing API Key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client, invalid_headers):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=invalid_headers,
    )
    assert response.status_code == 401
    assert "Invalid API Key" in response.json()["detail"]


def test_adjust_stock_success(client, valid_headers):
    """Test successful stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -20},
        headers=valid_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 80


def test_adjust_stock_nonexistent_sku(client, valid_headers):
    """Test stock adjustment for nonexistent SKU."""
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 10},
        headers=valid_headers,
    )
    assert response.status_code == 404


def test_create_reservation_success(client, valid_headers):
    """Test successful reservation creation."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, valid_headers):
    """Test reservation fails with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 30},
        headers=valid_headers,
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client, valid_headers):
    """Test idempotent reservation creation."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    # First request
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-idempotent"},
        headers=valid_headers,
    )
    assert response1.status_code == 201
    data1 = response1.json()
    id1 = data1["id"]
    created_at1 = data1["created_at"]

    # Second request with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-idempotent"},
        headers=valid_headers,
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["id"] == id1
    assert data2["created_at"] == created_at1

    # Verify only one reservation exists and stock was deducted once
    orders_response = client.get("/orders?page=1&size=10")
    # No orders yet, but we can verify by trying to get stock
    sku_info = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers=valid_headers,
    )
    assert sku_info.json()["available_stock"] == 70


def test_confirm_reservation_success(client, valid_headers):
    """Test successful reservation confirmation."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=valid_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert "order_id" in data


def test_confirm_expired_reservation(client, valid_headers):
    """Test that expired reservation cannot be confirmed."""
    from unittest.mock import patch
    from datetime import datetime, timedelta
    import commerce_service.service

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    reservation_id = res.json()["id"]

    # Mock time to make reservation old
    with patch("commerce_service.service.datetime") as mock_datetime:
        old_time = datetime.utcnow() - timedelta(seconds=400)
        mock_datetime.utcnow.return_value = old_time

        # Update the database directly to simulate old reservation
        from commerce_service.app import repository
        session = repository.get_session()
        from commerce_service.models import Reservation

        session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).update({"created_at": old_time})
        session.commit()
        session.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=valid_headers,
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]


def test_confirm_non_pending_reservation(client, valid_headers):
    """Test confirmation of non-pending reservation fails."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    reservation_id = res.json()["id"]

    # Confirm once
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=valid_headers,
    )

    # Try to confirm again
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=valid_headers,
    )
    assert response.status_code == 400


def test_cancel_reservation_success(client, valid_headers):
    """Test successful reservation cancellation."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=valid_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    # Verify stock was restored
    stock_check = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers=valid_headers,
    )
    assert stock_check.json()["available_stock"] == 100


def test_cancel_non_pending_reservation(client, valid_headers):
    """Test cancellation of non-pending reservation fails."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers=valid_headers,
    )
    reservation_id = res.json()["id"]

    # Confirm reservation
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=valid_headers,
    )

    # Try to cancel confirmed reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=valid_headers,
    )
    assert response.status_code == 400


def test_get_orders_empty(client):
    """Test getting orders when none exist."""
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 0
    assert len(data["orders"]) == 0


def test_get_orders_pagination(client, valid_headers):
    """Test orders pagination."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=valid_headers,
    )

    # Create multiple orders
    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key-{i}"},
            headers=valid_headers,
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=valid_headers,
        )

    # Test first page
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["orders"]) == 10

    # Test second page
    response = client.get("/orders?page=2&size=10")
    data = response.json()
    assert len(data["orders"]) == 5


def test_unauthorized_mutation_missing_key(client):
    """Test mutation without API key returns 401."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_unauthorized_mutation_invalid_key(client, invalid_headers):
    """Test mutation with invalid API key returns 401."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=invalid_headers,
    )
    assert response.status_code == 401


def test_happy_path_complete_workflow(client, valid_headers):
    """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 50},
        headers=valid_headers,
    )
    assert sku_response.status_code == 201
    assert sku_response.json()["available_stock"] == 50

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 20, "idempotency_key": "order-key-1"},
        headers=valid_headers,
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]
    assert res_response.json()["status"] == "PENDING"

    # Verify stock was deducted
    stock_check = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 0},
        headers=valid_headers,
    )
    assert stock_check.json()["available_stock"] == 30

    # Confirm reservation
    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=valid_headers,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"

    # Get orders
    orders_response = client.get("/orders?page=1&size=10")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert data["total"] == 1
    assert data["orders"][0]["reservation_id"] == reservation_id
