"""Integration tests for the API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService

client = TestClient(app)
API_KEY = "secret-api-key"
INVALID_API_KEY = "invalid-key"


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the database before each test."""
    from src.commerce_service import app as app_module
    app_module.db = Database(":memory:")
    app_module.service = CommerceService(app_module.db)


def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_authorized():
    """Test creating a SKU with valid API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_unauthorized():
    """Test creating a SKU without API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key():
    """Test creating a SKU with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": INVALID_API_KEY},
    )
    assert response.status_code == 401


def test_adjust_stock_authorized():
    """Test adjusting stock with valid API key."""
    # Create SKU first
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Adjust stock
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -50},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 50


def test_adjust_stock_unauthorized():
    """Test adjusting stock without API key."""
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -50},
    )
    assert response.status_code == 403


def test_create_reservation_sufficient_stock():
    """Test creating a reservation with sufficient stock."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock():
    """Test creating a reservation with insufficient stock."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 10},
        headers={"X-API-Key": API_KEY},
    )

    # Try to create reservation exceeding stock
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    data = response.json()
    assert "Insufficient stock" in data["detail"]


def test_create_reservation_idempotency():
    """Test idempotent reservation creation."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create first reservation
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    # Create second reservation with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    # Should return the same reservation
    assert data1["id"] == data2["id"]
    assert data1["sku"] == data2["sku"]
    assert data1["quantity"] == data2["quantity"]


def test_create_reservation_unauthorized():
    """Test creating a reservation without API key."""
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
    )
    assert response.status_code == 403


def test_confirm_reservation_success():
    """Test confirming a reservation."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert "order_id" in data


def test_confirm_reservation_expired():
    """Test confirming an expired reservation."""
    import time
    from unittest.mock import patch

    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    # Mock datetime to simulate expiration
    from datetime import datetime, timedelta
    future_time = datetime.utcnow() + timedelta(seconds=310)

    with patch("src.commerce_service.service.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = future_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Reservation expired" in data["detail"]


def test_confirm_reservation_invalid_state():
    """Test confirming a non-PENDING reservation."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create and confirm reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    # Try to confirm again
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_cancel_reservation_success():
    """Test cancelling a reservation."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_unauthorized():
    """Test cancelling a reservation without API key."""
    response = client.post(
        "/reservations/1/cancel",
    )
    assert response.status_code == 403


def test_get_orders_pagination():
    """Test getting orders with pagination."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create and confirm multiple reservations
    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idempotency-{i}",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    # Test first page
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["size"] == 10

    # Test second page
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["total"] == 15
    assert data["page"] == 2
    assert data["size"] == 10


def test_happy_path_workflow():
    """Test complete happy path: SKU -> Reserve -> Confirm -> Order lookup."""
    # 1. Create SKU
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-HAPPY", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert sku_response.status_code == 201

    # 2. Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-HAPPY", "quantity": 25, "idempotency_key": "happy-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    # 3. Confirm reservation
    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["order_id"]

    # 4. Lookup orders
    orders_response = client.get("/orders?page=1&size=10")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert data["total"] == 1
    assert data["orders"][0]["id"] == order_id
    assert data["orders"][0]["reservation_id"] == reservation_id
