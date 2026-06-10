"""Tests for the FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from commerce_service.app import app, service


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def setup_db(client):
    """Setup test database with sample data."""
    # Create a SKU
    client.post(
        "/skus",
        json={"sku_code": "PROD001", "name": "Product 1"},
        headers={"X-API-Key": "test-key"},
    )
    # Add stock
    client.post(
        "/stock/adjust",
        json={"sku_code": "PROD001", "delta": 100},
        headers={"X-API-Key": "test-key"},
    )
    return client


class TestHealth:
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku_code": "PROD001", "name": "Product 1"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        assert response.json()["sku_code"] == "PROD001"

    def test_create_sku_missing_api_key(self, client):
        """Test creating SKU without API key."""
        response = client.post(
            "/skus",
            json={"sku_code": "PROD001", "name": "Product 1"},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_payload(self, client):
        """Test creating SKU with invalid payload."""
        response = client.post(
            "/skus",
            json={"sku_code": "", "name": "Product 1"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 422


class TestStockEndpoints:
    def test_adjust_stock_success(self, client):
        """Test adjusting stock."""
        # First create a SKU
        client.post(
            "/skus",
            json={"sku_code": "PROD001", "name": "Product 1"},
            headers={"X-API-Key": "test-key"},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku_code": "PROD001", "delta": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["available"] == 100

    def test_adjust_stock_sku_not_found(self, client):
        """Test adjusting stock for non-existent SKU."""
        response = client.post(
            "/stock/adjust",
            json={"sku_code": "NONEXISTENT", "delta": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 404

    def test_adjust_stock_missing_api_key(self, client):
        """Test adjusting stock without API key."""
        response = client.post(
            "/stock/adjust",
            json={"sku_code": "PROD001", "delta": 100},
        )
        assert response.status_code == 403


class TestReservationEndpoints:
    def test_create_reservation_success(self, setup_db):
        """Test creating a reservation."""
        client = setup_db
        response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        assert response.json()["quantity"] == 10
        assert response.json()["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, setup_db):
        """Test reservation fails with insufficient stock."""
        client = setup_db
        response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 150, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotency(self, setup_db):
        """Test idempotent reservation creation."""
        client = setup_db
        # First request
        response1 = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res1_id = response1.json()["id"]

        # Second request with same idempotency key
        response2 = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res2_id = response2.json()["id"]

        assert res1_id == res2_id
        assert response2.status_code == 201

    def test_create_reservation_unauthorized(self, setup_db):
        """Test creating reservation without API key."""
        client = setup_db
        response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
        )
        assert response.status_code == 403

    def test_confirm_reservation_success(self, setup_db):
        """Test confirming a reservation."""
        client = setup_db
        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]

        # Confirm it
        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "confirmed"

    def test_confirm_reservation_not_found(self, client):
        """Test confirming non-existent reservation."""
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 404

    def test_confirm_reservation_unauthorized(self, setup_db):
        """Test confirming reservation without API key."""
        client = setup_db
        res_response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]

        response = client.post(f"/reservations/{res_id}/confirm")
        assert response.status_code == 403

    def test_cancel_reservation_success(self, setup_db):
        """Test cancelling a reservation."""
        client = setup_db
        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]

        # Cancel it
        cancel_response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

    def test_cancel_reservation_not_found(self, client):
        """Test cancelling non-existent reservation."""
        response = client.post(
            "/reservations/999/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        """Test listing orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert response.json()["orders"] == []

    def test_list_orders_with_items(self, setup_db):
        """Test listing orders with items."""
        client = setup_db
        # Create and confirm a reservation
        res_response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )

        # List orders
        response = client.get("/orders")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert len(response.json()["orders"]) == 1

    def test_list_orders_pagination(self, setup_db):
        """Test pagination of orders."""
        client = setup_db
        # Create multiple orders
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={
                    "sku_code": "PROD001",
                    "quantity": 1,
                    "idempotency_key": f"req-{i}",
                },
                headers={"X-API-Key": "test-key"},
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": "test-key"},
            )

        # Test with limit
        response = client.get("/orders?offset=0&limit=3")
        assert response.status_code == 200
        assert len(response.json()["orders"]) == 3
        assert response.json()["total"] == 5
        assert response.json()["limit"] == 3

        # Test second page
        response2 = client.get("/orders?offset=3&limit=3")
        assert len(response2.json()["orders"]) == 2

    def test_get_order(self, setup_db):
        """Test retrieving a specific order."""
        client = setup_db
        # Create and confirm reservation
        res_response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 10, "idempotency_key": "req-001"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]

        order_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        order_id = order_response.json()["id"]

        # Get the order
        get_response = client.get(f"/orders/{order_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == order_id
        assert get_response.json()["status"] == "confirmed"

    def test_get_order_not_found(self, client):
        """Test retrieving non-existent order."""
        response = client.get("/orders/999")
        assert response.status_code == 404


class TestCompleteWorkflow:
    def test_complete_order_workflow(self, client):
        """Test a complete order workflow."""
        # 1. Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD001", "name": "Product 1"},
            headers={"X-API-Key": "test-key"},
        )
        assert sku_response.status_code == 201

        # 2. Adjust stock
        stock_response = client.post(
            "/stock/adjust",
            json={"sku_code": "PROD001", "delta": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert stock_response.status_code == 200
        assert stock_response.json()["available"] == 100

        # 3. Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku_code": "PROD001", "quantity": 25, "idempotency_key": "order-1"},
            headers={"X-API-Key": "test-key"},
        )
        assert res_response.status_code == 201
        res_id = res_response.json()["id"]

        # 4. Confirm reservation to create order
        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert confirm_response.status_code == 200
        order = confirm_response.json()
        assert order["status"] == "confirmed"
        assert len(order["items"]) == 1
        assert order["items"][0]["quantity"] == 25

        # 5. List orders
        list_response = client.get("/orders")
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
