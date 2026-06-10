"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, _repo, _service


@pytest.fixture
def client():
    """Create a test client."""
    _repo.clear_db()
    return TestClient(app)


@pytest.fixture
def api_key():
    """API key for authenticated requests."""
    return "test-api-key"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        response = client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PROD-001"
        assert data["stock_qty"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post("/skus", json={"sku": "PROD-001", "stock_qty": 100})
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, api_key):
        # Create SKU first
        create_resp = client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )
        sku_id = create_resp.json()["id"]

        # Adjust stock
        response = client.post(
            f"/skus/{sku_id}/stock",
            json={"delta": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["stock_qty"] == 150

    def test_adjust_stock_not_found(self, client, api_key):
        response = client.post(
            "/skus/999/stock",
            json={"delta": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )

        # Create reservation
        response = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PROD-001"
        assert data["qty"] == 30
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 20},
            headers={"X-API-Key": api_key},
        )

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )

        # Create first reservation
        response1 = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        id1 = response1.json()["id"]

        # Retry with same key
        response2 = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 50, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        id2 = response2.json()["id"]
        qty2 = response2.json()["qty"]

        assert id1 == id2
        assert qty2 == 30  # Original qty preserved

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
        )
        assert response.status_code == 401


class TestConfirmReservation:
    def test_confirm_reservation_success(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )

        # Create reservation
        res_resp = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        # Confirm reservation
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "PROD-001"
        assert data["qty"] == 30
        assert data["status"] == "pending"  # Order status is pending

    def test_confirm_reservation_not_found(self, client, api_key):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404

    def test_confirm_reservation_unauthorized(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )

        # Create reservation
        res_resp = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        # Try to confirm without API key
        response = client.post(f"/reservations/{res_id}/confirm")
        assert response.status_code == 401


class TestCancelReservation:
    def test_cancel_reservation_success(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )

        # Create reservation
        res_resp = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        # Cancel reservation
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_reservation_not_found(self, client, api_key):
        response = client.post(
            "/reservations/999/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["total_pages"] == 0

    def test_get_orders_with_items(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 100},
            headers={"X-API-Key": api_key},
        )

        # Create and confirm reservation
        res_resp = client.post(
            "/reservations",
            json={"sku": "PROD-001", "qty": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )

        # Get orders
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["sku"] == "PROD-001"

    def test_get_orders_pagination(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock_qty": 1000},
            headers={"X-API-Key": api_key},
        )

        # Create and confirm 25 orders
        for i in range(25):
            res_resp = client.post(
                "/reservations",
                json={"sku": "PROD-001", "qty": 1, "idempotency_key": f"key-{i}"},
                headers={"X-API-Key": api_key},
            )
            res_id = res_resp.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        # Get page 1
        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 3

        # Get page 2
        response = client.get("/orders?page=2&page_size=10")
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 2

        # Get page 3
        response = client.get("/orders?page=3&page_size=10")
        data = response.json()
        assert len(data["items"]) == 5

    def test_get_orders_invalid_pagination(self, client):
        response = client.get("/orders?page=0")
        assert response.status_code == 422  # Pydantic validation error

        response = client.get("/orders?page_size=0")
        assert response.status_code == 422

        response = client.get("/orders?page_size=101")
        assert response.status_code == 422
