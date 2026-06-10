"""Tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_service():
    """Reset service with in-memory database before each test."""
    repo = Repository(db_path=":memory:")
    service = CommerceService(repo)

    # Monkey patch the dependencies
    from commerce_service import app as app_module

    app_module._repo = repo
    app_module._service = service

    yield


def get_headers(api_key="test-api-key-12345"):
    return {"X-API-Key": api_key}


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        assert response.status_code == 201
        assert response.json()["sku_id"] == "SKU123"

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers("invalid-key"),
        )
        assert response.status_code == 401

    def test_create_sku_no_api_key(self, client):
        response = client.post(
            "/skus", json={"sku_id": "SKU123", "name": "Test Product"}
        )
        assert response.status_code == 403

    def test_adjust_stock_success(self, client):
        # Create SKU first
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )

        # Adjust stock
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )
        assert response.status_code == 200
        assert response.json()["new_available"] == 100

    def test_adjust_stock_sku_not_found(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "NONEXISTENT", "adjustment": 100},
            headers=get_headers(),
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )

        # Create reservation
        response = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 10,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
        assert response.json()["quantity"] == 10

    def test_create_reservation_insufficient_stock(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 50},
            headers=get_headers(),
        )

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 100,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        assert response.status_code == 409

    def test_create_reservation_idempotency(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )

        # Create first reservation
        response1 = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 10,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        res_id1 = response1.json()["id"]

        # Retry with same idempotency key
        response2 = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 10,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        res_id2 = response2.json()["id"]

        assert res_id1 == res_id2
        assert response2.status_code == 201

    def test_confirm_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )

        # Create reservation
        res = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 10,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        res_id = res.json()["id"]

        # Confirm
        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers=get_headers(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_cancel_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )

        # Create reservation
        res = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 10,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        res_id = res.json()["id"]

        # Cancel
        response = client.post(
            f"/reservations/{res_id}/cancel",
            json={},
            headers=get_headers(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_releases_stock(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 50},
            headers=get_headers(),
        )

        # Create and cancel first reservation
        res1 = client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 50,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )
        res_id1 = res1.json()["id"]

        client.post(
            f"/reservations/{res_id1}/cancel",
            json={},
            headers=get_headers(),
        )

        # Should be able to create new reservation with released stock
        response = client.post(
            "/reservations",
            json={
                "order_id": "ORDER2",
                "sku_id": "SKU123",
                "quantity": 50,
                "idempotency_key": "KEY2",
            },
            headers=get_headers(),
        )
        assert response.status_code == 201


class TestOrderEndpoints:
    def test_get_order(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )

        # Create reservation
        client.post(
            "/reservations",
            json={
                "order_id": "ORDER1",
                "sku_id": "SKU123",
                "quantity": 10,
                "idempotency_key": "KEY1",
            },
            headers=get_headers(),
        )

        # Get order
        response = client.get("/orders/ORDER1")
        assert response.status_code == 200
        assert response.json()["order"]["id"] == "ORDER1"
        assert len(response.json()["reservations"]) == 1

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders/NONEXISTENT")
        assert response.status_code == 404

    def test_list_orders_pagination(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 1000},
            headers=get_headers(),
        )

        # Create 15 orders
        for i in range(15):
            client.post(
                "/reservations",
                json={
                    "order_id": f"ORDER{i}",
                    "sku_id": "SKU123",
                    "quantity": 1,
                    "idempotency_key": f"KEY{i}",
                },
                headers=get_headers(),
            )

        # Test first page
        response = client.get("/orders?offset=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["offset"] == 0
        assert data["limit"] == 10

        # Test second page
        response = client.get("/orders?offset=10&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["total"] == 15

    def test_list_orders_default_pagination(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU123", "name": "Test Product"},
            headers=get_headers(),
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU123", "adjustment": 100},
            headers=get_headers(),
        )

        # Create 5 orders
        for i in range(5):
            client.post(
                "/reservations",
                json={
                    "order_id": f"ORDER{i}",
                    "sku_id": "SKU123",
                    "quantity": 1,
                    "idempotency_key": f"KEY{i}",
                },
                headers=get_headers(),
            )

        # Test default pagination
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["total"] == 5
