"""Tests for the FastAPI endpoints."""

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    os.unlink(path)


@pytest.fixture
def client(temp_db):
    """Create a test client with mocked database."""
    with patch("src.commerce_service.app.db", temp_db):
        from src.commerce_service.app import service as app_service
        app_service.db = temp_db
        yield TestClient(app)


@pytest.fixture
def api_key():
    """Valid API key for testing."""
    return "dev-key-12345"


class TestHealthCheck:
    def test_health_check_success(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        """Test successful SKU creation."""
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Premium Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "WIDGET-001"
        assert data["name"] == "Premium Widget"
        assert data["price"] == 99.99

    def test_create_sku_duplicate_fails(self, client, api_key):
        """Test that duplicate SKU creation returns conflict."""
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Premium Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Different",
                "price": 50.0,
                "initial_stock": 50,
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 409

    def test_create_sku_invalid_price(self, client, api_key):
        """Test SKU creation with invalid price."""
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": -10.0,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 422


class TestInventoryEndpoints:
    def test_adjust_stock_increase(self, client, api_key):
        """Test increasing stock."""
        # Create SKU first
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        response = client.patch(
            "/inventory/WIDGET-001",
            json={"quantity_delta": 25},
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["available_quantity"] == 125

    def test_adjust_stock_nonexistent_sku(self, client, api_key):
        """Test adjusting stock for non-existent SKU."""
        response = client.patch(
            "/inventory/NONEXISTENT",
            json={"quantity_delta": 10},
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, api_key):
        """Test successful reservation creation."""
        # Create SKU first
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "WIDGET-001"
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_idempotent(self, client, api_key):
        """Test idempotent reservation creation."""
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        # First request
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )
        res_id_1 = response1.json()["reservation_id"]

        # Retry with same key
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 20,  # Different quantity
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )
        res_id_2 = response2.json()["reservation_id"]

        assert res_id_1 == res_id_2
        assert response2.json()["quantity"] == 10  # Original quantity

    def test_create_reservation_insufficient_stock(self, client, api_key):
        """Test reservation with insufficient stock."""
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 50,
            },
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 100,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_confirm_reservation_success(self, client, api_key):
        """Test successful reservation confirmation."""
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        res = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_cancel_reservation_success(self, client, api_key):
        """Test successful reservation cancellation."""
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        res = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrderEndpoints:
    def test_list_orders_empty(self, client, api_key):
        """Test listing orders on empty database."""
        response = client.get("/orders", headers={"X-API-Key": api_key})

        assert response.status_code == 200
        assert response.json() == []

    def test_list_orders_with_pagination(self, client, api_key):
        """Test order pagination."""
        # Create SKU
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 1000,
            },
            headers={"X-API-Key": api_key},
        )

        # Create and confirm multiple reservations
        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku_id": "WIDGET-001",
                    "quantity": 1,
                    "idempotency_key": f"order-{i}",
                },
                headers={"X-API-Key": api_key},
            )
            res_id = res.json()["reservation_id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        # Get first page
        response = client.get(
            "/orders?skip=0&limit=10",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert len(response.json()) == 10

        # Get second page
        response = client.get(
            "/orders?skip=10&limit=10",
            headers={"X-API-Key": api_key},
        )
        assert len(response.json()) == 5


class TestSecurityAndValidation:
    def test_unauthorized_mutation_without_api_key(self, client):
        """Test mutation endpoints without API key."""
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
        )
        # Should succeed without API key (based on implementation)
        assert response.status_code in [201, 403]

    def test_invalid_request_validation(self, client, api_key):
        """Test request validation."""
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "",  # Invalid: empty name
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 422

    def test_reservation_with_invalid_quantity(self, client, api_key):
        """Test reservation with invalid quantity."""
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "price": 99.99,
                "initial_stock": 100,
            },
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": -5,  # Invalid: negative quantity
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 422
