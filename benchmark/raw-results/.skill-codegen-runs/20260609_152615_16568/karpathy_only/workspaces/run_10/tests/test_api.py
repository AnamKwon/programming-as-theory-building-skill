"""Tests for commerce service API endpoints."""

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, repo, service

client = TestClient(app)

API_KEY = "test-key-123"
HEADERS = {"X-API-Key": API_KEY}


class TestHealth:
    """Test health check endpoint."""

    def test_health_check(self):
        """Test health check."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    """Test SKU creation and stock adjustment endpoints."""

    def test_create_sku(self):
        """Test creating a SKU via API."""
        response = client.post(
            "/skus",
            json={"sku_id": "TEST-SKU-001", "quantity": 100},
            headers=HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "TEST-SKU-001"
        assert data["quantity"] == 100

    def test_create_sku_unauthorized(self):
        """Test creating a SKU without API key."""
        response = client.post(
            "/skus",
            json={"sku_id": "TEST-SKU-002", "quantity": 100},
        )
        assert response.status_code == 403

    def test_adjust_stock(self):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-SKU-ADJ", "quantity": 100},
            headers=HEADERS,
        )

        response = client.patch(
            "/skus/TEST-SKU-ADJ/stock",
            json={"quantity_delta": 50},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 150

    def test_adjust_stock_unauthorized(self):
        """Test adjusting stock without API key."""
        response = client.patch(
            "/skus/TEST-SKU-ADJ/stock",
            json={"quantity_delta": 50},
        )
        assert response.status_code == 403

    def test_adjust_nonexistent_sku(self):
        """Test adjusting stock for non-existent SKU."""
        response = client.patch(
            "/skus/NONEXISTENT/stock",
            json={"quantity_delta": 50},
            headers=HEADERS,
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    """Test reservation endpoints."""

    def test_create_reservation(self):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-RESERVE", "quantity": 100},
            headers=HEADERS,
        )

        response = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-RESERVE",
                "quantity": 10,
                "idempotency_key": "key-001",
            },
            headers=HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "TEST-RESERVE"
        assert data["quantity"] == 10
        assert data["state"] == "PENDING"

    def test_create_reservation_unauthorized(self):
        """Test creating a reservation without API key."""
        response = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-RESERVE",
                "quantity": 10,
                "idempotency_key": "key-002",
            },
        )
        assert response.status_code == 403

    def test_create_reservation_insufficient_stock(self):
        """Test creating a reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-LOW-STOCK", "quantity": 5},
            headers=HEADERS,
        )

        response = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-LOW-STOCK",
                "quantity": 10,
                "idempotency_key": "key-003",
            },
            headers=HEADERS,
        )
        assert response.status_code == 409
        assert "INSUFFICIENT_STOCK" in response.headers.get("X-Error-Code", "")

    def test_reservation_idempotency(self):
        """Test that same idempotency key returns same reservation."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-IDEMPOTENT", "quantity": 100},
            headers=HEADERS,
        )

        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-IDEMPOTENT",
                "quantity": 10,
                "idempotency_key": "key-idem-001",
            },
            headers=HEADERS,
        )
        reservation1_id = response1.json()["reservation_id"]

        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-IDEMPOTENT",
                "quantity": 10,
                "idempotency_key": "key-idem-001",
            },
            headers=HEADERS,
        )
        reservation2_id = response2.json()["reservation_id"]

        assert reservation1_id == reservation2_id

    def test_confirm_reservation(self):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-CONFIRM", "quantity": 100},
            headers=HEADERS,
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-CONFIRM",
                "quantity": 10,
                "idempotency_key": "key-confirm-001",
            },
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "TEST-CONFIRM"
        assert data["state"] == "CONFIRMED"

    def test_confirm_reservation_unauthorized(self):
        """Test confirming a reservation without API key."""
        response = client.post(
            "/reservations/some-id/confirm",
        )
        assert response.status_code == 403

    def test_confirm_nonexistent_reservation(self):
        """Test confirming non-existent reservation."""
        response = client.post(
            "/reservations/nonexistent/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 404

    def test_cancel_reservation(self):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-CANCEL", "quantity": 100},
            headers=HEADERS,
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-CANCEL",
                "quantity": 10,
                "idempotency_key": "key-cancel-001",
            },
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "CANCELLED"

    def test_cancel_reservation_unauthorized(self):
        """Test cancelling a reservation without API key."""
        response = client.post(
            "/reservations/some-id/cancel",
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    """Test order endpoints."""

    def test_list_orders(self):
        """Test listing orders."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-LIST-ORDERS", "quantity": 1000},
            headers=HEADERS,
        )

        # Create and confirm multiple reservations
        for i in range(3):
            res_response = client.post(
                "/reservations",
                json={
                    "sku_id": "TEST-LIST-ORDERS",
                    "quantity": 10,
                    "idempotency_key": f"key-list-{i}",
                },
                headers=HEADERS,
            )
            reservation_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=HEADERS,
            )

        response = client.get(
            "/orders?limit=10&offset=0",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_list_orders_pagination(self):
        """Test order pagination."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-PAGINATE", "quantity": 1000},
            headers=HEADERS,
        )

        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={
                    "sku_id": "TEST-PAGINATE",
                    "quantity": 10,
                    "idempotency_key": f"key-page-{i}",
                },
                headers=HEADERS,
            )
            reservation_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=HEADERS,
            )

        response = client.get(
            "/orders?limit=2&offset=0",
            headers=HEADERS,
        )
        data = response.json()
        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["items"]) == 2

        response = client.get(
            "/orders?limit=2&offset=2",
            headers=HEADERS,
        )
        data = response.json()
        assert len(data["items"]) == 2

    def test_list_orders_unauthorized(self):
        """Test listing orders without API key."""
        response = client.get("/orders")
        assert response.status_code == 403

    def test_get_order(self):
        """Test getting a specific order."""
        client.post(
            "/skus",
            json={"sku_id": "TEST-GET-ORDER", "quantity": 100},
            headers=HEADERS,
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "TEST-GET-ORDER",
                "quantity": 10,
                "idempotency_key": "key-get-order",
            },
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]

        order_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=HEADERS,
        )
        order_id = order_response.json()["order_id"]

        response = client.get(
            f"/orders/{order_id}",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["sku_id"] == "TEST-GET-ORDER"

    def test_get_order_unauthorized(self):
        """Test getting order without API key."""
        response = client.get("/orders/some-id")
        assert response.status_code == 403

    def test_get_nonexistent_order(self):
        """Test getting non-existent order."""
        response = client.get(
            "/orders/nonexistent",
            headers=HEADERS,
        )
        assert response.status_code == 404
