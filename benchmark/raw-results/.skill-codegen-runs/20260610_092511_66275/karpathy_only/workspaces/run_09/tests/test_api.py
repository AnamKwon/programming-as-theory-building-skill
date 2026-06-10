"""Tests for the FastAPI endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Set up a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        monkeypatch.setattr(
            "commerce_service.app.repository", Repository(db_path)
        )
        monkeypatch.setattr(
            "commerce_service.app.service", Service(Repository(db_path))
        )
        yield


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def headers():
    """Return API key headers."""
    return {"X-API-Key": "test-key"}


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    """Tests for SKU endpoints."""

    def test_create_sku_success(self, client, headers):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "SKU001"
        assert data["name"] == "Widget"
        assert data["current_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        """Test creating a SKU without API key."""
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_list_skus(self, client, headers):
        """Test listing SKUs."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )
        client.post(
            "/skus",
            json={"id": "SKU002", "name": "Gadget", "initial_stock": 50},
            headers=headers,
        )

        response = client.get("/skus")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_adjust_stock_increase(self, client, headers):
        """Test increasing stock."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        response = client.patch(
            "/skus/SKU001/stock",
            json={"adjustment": 50},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["current_stock"] == 150

    def test_adjust_stock_unauthorized(self, client, headers):
        """Test adjusting stock without API key."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        response = client.patch(
            "/skus/SKU001/stock",
            json={"adjustment": 50},
        )
        assert response.status_code == 401

    def test_adjust_stock_not_found(self, client, headers):
        """Test adjusting stock for non-existent SKU."""
        response = client.patch(
            "/skus/NONEXISTENT/stock",
            json={"adjustment": 50},
            headers=headers,
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    """Tests for reservation endpoints."""

    def test_create_reservation_success(self, client, headers):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_unauthorized(self, client, headers):
        """Test creating a reservation without API key."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
        )
        assert response.status_code == 401

    def test_create_reservation_insufficient_stock(self, client, headers):
        """Test creating a reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 10},
            headers=headers,
        )

        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 20, "ttl_seconds": 300},
            headers=headers,
        )
        assert response.status_code == 409

    def test_create_reservation_not_found(self, client, headers):
        """Test creating a reservation for non-existent SKU."""
        response = client.post(
            "/reservations",
            json={"sku_id": "NONEXISTENT", "quantity": 10, "ttl_seconds": 300},
            headers=headers,
        )
        assert response.status_code == 404

    def test_idempotent_reservation_retry(self, client, headers):
        """Test idempotent reservation creation."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        # First request
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "ttl_seconds": 300,
                "idempotency_key": "key123",
            },
            headers=headers,
        )
        res_id_1 = response1.json()["id"]

        # Retry with same idempotency key
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "ttl_seconds": 300,
                "idempotency_key": "key123",
            },
            headers=headers,
        )
        res_id_2 = response2.json()["id"]

        assert res_id_1 == res_id_2

    def test_confirm_reservation_success(self, client, headers):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
            headers=headers,
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reservation"]["status"] == "confirmed"
        assert "order" in data

    def test_confirm_reservation_not_found(self, client, headers):
        """Test confirming non-existent reservation."""
        response = client.post(
            "/reservations/NONEXISTENT/confirm",
            headers=headers,
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client, headers):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
            headers=headers,
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_reservation_unauthorized(self, client, headers):
        """Test cancelling a reservation without API key."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
            headers=headers,
        )
        res_id = res_response.json()["id"]

        response = client.post(f"/reservations/{res_id}/cancel")
        assert response.status_code == 401

    def test_cancel_reservation_not_found(self, client, headers):
        """Test cancelling non-existent reservation."""
        response = client.post(
            "/reservations/NONEXISTENT/cancel",
            headers=headers,
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    """Tests for order endpoints."""

    def test_list_orders_empty(self, client):
        """Test listing orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 0
        assert data["has_more"] is False

    def test_list_orders_with_pagination(self, client, headers):
        """Test pagination in order listing."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 1000},
            headers=headers,
        )

        # Create 5 orders
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
                headers=headers,
            )
            res_id = res_response.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=headers)

        # Paginate with limit=2
        response1 = client.get("/orders?limit=2&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["orders"]) == 2
        assert data1["has_more"] is True

        response2 = client.get("/orders?limit=2&offset=2")
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 2

    def test_get_order_success(self, client, headers):
        """Test retrieving a single order."""
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers=headers,
        )

        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "ttl_seconds": 300},
            headers=headers,
        )
        res_id = res_response.json()["id"]

        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=headers,
        )
        order_id = confirm_response.json()["order"]["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id

    def test_get_order_not_found(self, client):
        """Test retrieving a non-existent order."""
        response = client.get("/orders/NONEXISTENT")
        assert response.status_code == 404
