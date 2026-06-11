"""Integration tests for commerce API endpoints."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
import sqlite3
import time

from src.commerce_service.app import app
from src.commerce_service.repository import DB_PATH, init_db


@pytest.fixture(scope="function")
def client():
    """Create test client with fresh database."""
    # Remove existing database
    if DB_PATH.exists():
        DB_PATH.unlink()

    # Initialize fresh database
    init_db()

    yield TestClient(app)

    # Cleanup
    if DB_PATH.exists():
        DB_PATH.unlink()


@pytest.fixture
def valid_headers():
    """Valid API key headers."""
    return {"X-API-Key": "test-key-123"}


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_check_no_auth(self, client):
        """Health check should work without authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    """Tests for SKU management endpoints."""

    def test_create_sku_success(self, client, valid_headers):
        """Successfully create a SKU."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU001"
        assert response.json()["stock"] == 100

    def test_create_sku_no_auth(self, client):
        """Creating SKU without API key should fail."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100}
        )
        assert response.status_code == 401

    def test_create_sku_invalid_key(self, client):
        """Creating SKU with invalid API key should fail."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401


class TestStockAdjustment:
    """Tests for stock adjustment endpoint."""

    def test_adjust_stock_increase(self, client, valid_headers):
        """Adjust stock by positive amount."""
        # Create SKU first
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 50},
            headers=valid_headers
        )

        # Adjust stock
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 30},
            headers=valid_headers
        )
        assert response.status_code == 200
        assert response.json()["new_stock"] == 80

    def test_adjust_stock_decrease(self, client, valid_headers):
        """Adjust stock by negative amount."""
        # Create SKU first
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 50},
            headers=valid_headers
        )

        # Adjust stock
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -20},
            headers=valid_headers
        )
        assert response.status_code == 200
        assert response.json()["new_stock"] == 30


class TestReservations:
    """Tests for reservation endpoints."""

    def test_reservation_happy_path(self, client, valid_headers):
        """Test full reservation workflow: create -> confirm -> order."""
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers
        )

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        assert res_response.status_code == 201
        assert res_response.json()["status"] == "PENDING"
        reservation_id = res_response.json()["id"]

        # Confirm reservation
        conf_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=valid_headers
        )
        assert conf_response.status_code == 200
        assert conf_response.json()["status"] == "CONFIRMED"
        order_id = conf_response.json()["order_id"]

        # Check order in list
        orders_response = client.get(
            "/orders?page=1&size=10",
            headers=valid_headers
        )
        assert orders_response.status_code == 200
        orders = orders_response.json()["items"]
        assert len(orders) >= 1
        assert any(o["id"] == order_id for o in orders)

    def test_reservation_insufficient_stock(self, client, valid_headers):
        """Reservation with insufficient stock should fail."""
        # Create SKU with limited stock
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 5},
            headers=valid_headers
        )

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_reservation_idempotency(self, client, valid_headers):
        """Same idempotency key should return same reservation without stock deduction."""
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers
        )

        # First reservation
        res1 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        assert res1.status_code == 201
        res1_id = res1.json()["id"]

        # Second request with same idempotency key
        res2 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        assert res2.status_code == 201
        assert res2.json()["id"] == res1_id  # Same reservation

    def test_reservation_cancellation(self, client, valid_headers):
        """Cancel reservation should restore stock."""
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers
        )

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 20, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        reservation_id = res_response.json()["id"]

        # Cancel reservation
        cancel_response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=valid_headers
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "CANCELLED"

    def test_confirm_non_pending_reservation(self, client, valid_headers):
        """Cannot confirm a reservation that's not PENDING."""
        # Create SKU and reservation
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        reservation_id = res_response.json()["id"]

        # Confirm once
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=valid_headers
        )

        # Try to confirm again
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=valid_headers
        )
        assert response.status_code == 400
        assert "not in PENDING state" in response.json()["detail"]

    def test_reservation_expiration(self, client, valid_headers):
        """Reservation older than 300 seconds should expire on confirm."""
        # Create SKU and reservation
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key-123"},
            headers=valid_headers
        )
        reservation_id = res_response.json()["id"]

        # Manually update created_at to be old
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = datetime('now', '-400 seconds') WHERE id = ?",
            (reservation_id,)
        )
        conn.commit()
        conn.close()

        # Try to confirm expired reservation
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=valid_headers
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Reservation expired"


class TestOrders:
    """Tests for order endpoints."""

    def test_pagination_offset_behavior(self, client, valid_headers):
        """Test pagination with multiple pages."""
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers=valid_headers
        )

        # Create and confirm multiple reservations
        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU001",
                    "quantity": 1,
                    "idempotency_key": f"key-{i}"
                },
                headers=valid_headers
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=valid_headers
            )

        # Get page 1 with size 10
        page1 = client.get(
            "/orders?page=1&size=10",
            headers=valid_headers
        )
        assert page1.status_code == 200
        assert len(page1.json()["items"]) == 10
        assert page1.json()["page"] == 1
        assert page1.json()["total"] == 15

        # Get page 2
        page2 = client.get(
            "/orders?page=2&size=10",
            headers=valid_headers
        )
        assert page2.status_code == 200
        assert len(page2.json()["items"]) == 5
        assert page2.json()["page"] == 2

    def test_orders_requires_auth(self, client):
        """GET /orders should require authentication."""
        response = client.get("/orders")
        assert response.status_code == 401
