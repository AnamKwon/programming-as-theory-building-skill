"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, repository, service
from commerce_service.models import ReservationStatus


@pytest.fixture(autouse=True)
def cleanup():
    """Clean up database before each test."""
    repository.cleanup_db()
    yield
    repository.cleanup_db()


client = TestClient(app)
VALID_KEY = "test-key-123"


class TestHealthCheck:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSKUEndpoints:
    def test_create_sku_success(self):
        response = client.post(
            "/skus",
            json={"code": "WIDGET-001", "name": "Blue Widget"},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "WIDGET-001"
        assert data["name"] == "Blue Widget"

    def test_create_sku_missing_api_key(self):
        response = client.post(
            "/skus",
            json={"code": "WIDGET-002", "name": "Red Widget"},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_api_key(self):
        response = client.post(
            "/skus",
            json={"code": "WIDGET-003", "name": "Green Widget"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self):
        sku_response = client.post(
            "/skus",
            json={"code": "WIDGET-004", "name": "Yellow Widget"},
            headers={"X-API-Key": VALID_KEY},
        )
        sku_id = sku_response.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/stock",
            json={"quantity": 100, "reason": "Initial stock"},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 100
        assert data["available"] == 100


class TestReservationEndpoints:
    def setup_method(self):
        """Create SKU and order for tests."""
        sku_response = client.post(
            "/skus",
            json={"code": "WIDGET-005", "name": "Purple Widget"},
            headers={"X-API-Key": VALID_KEY},
        )
        self.sku_id = sku_response.json()["id"]

        client.post(
            f"/skus/{self.sku_id}/stock",
            json={"quantity": 100},
            headers={"X-API-Key": VALID_KEY},
        )

        order_response = client.post(
            "/orders",
            headers={"X-API-Key": VALID_KEY},
        )
        self.order_id = order_response.json()["id"]

    def test_create_reservation_success(self):
        response = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idem-001",
                "expires_in_seconds": 3600,
            },
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == ReservationStatus.PENDING
        assert data["quantity"] == 10

    def test_create_reservation_insufficient_stock(self):
        response = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 500,
                "idempotency_key": "idem-002",
            },
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self):
        response1 = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idem-003",
            },
            headers={"X-API-Key": VALID_KEY},
        )
        res_id_1 = response1.json()["id"]

        response2 = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idem-003",
            },
            headers={"X-API-Key": VALID_KEY},
        )
        res_id_2 = response2.json()["id"]

        assert res_id_1 == res_id_2

    def test_confirm_reservation_success(self):
        res_response = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idem-004",
            },
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ReservationStatus.CONFIRMED

    def test_cancel_reservation_success(self):
        res_response = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idem-005",
            },
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ReservationStatus.CANCELLED

    def test_reservation_requires_api_key(self):
        response = client.post(
            "/reservations",
            json={
                "order_id": self.order_id,
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idem-006",
            },
        )
        assert response.status_code == 401


class TestOrderEndpoints:
    def setup_method(self):
        """Create SKU and order for tests."""
        sku_response = client.post(
            "/skus",
            json={"code": "WIDGET-006", "name": "Orange Widget"},
            headers={"X-API-Key": VALID_KEY},
        )
        self.sku_id = sku_response.json()["id"]

        client.post(
            f"/skus/{self.sku_id}/stock",
            json={"quantity": 100},
            headers={"X-API-Key": VALID_KEY},
        )

    def test_get_order_success(self):
        order_response = client.post(
            "/orders",
            headers={"X-API-Key": VALID_KEY},
        )
        order_id = order_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={
                "order_id": order_id,
                "sku_id": self.sku_id,
                "quantity": 5,
                "idempotency_key": "idem-007",
            },
            headers={"X-API-Key": VALID_KEY},
        )

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert len(data["items"]) == 1
        assert data["items"][0]["quantity"] == 5

    def test_get_nonexistent_order(self):
        response = client.get("/orders/999")
        assert response.status_code == 404

    def test_list_orders_pagination(self):
        for i in range(25):
            client.post(
                "/orders",
                headers={"X-API-Key": VALID_KEY},
            )

        response = client.get("/orders?skip=0&limit=20")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["items"]) == 20
        assert data["skip"] == 0
        assert data["limit"] == 20

        response = client.get("/orders?skip=20&limit=20")
        data = response.json()
        assert len(data["items"]) == 5

    def test_list_orders_default_pagination(self):
        for i in range(5):
            client.post(
                "/orders",
                headers={"X-API-Key": VALID_KEY},
            )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["limit"] == 20
