import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key_header():
    return {"X-API-Key": "test-api-key"}


@pytest.fixture
def invalid_api_key_header():
    return {"X-API-Key": "invalid-key"}


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoint:
    def test_create_sku_succeeds(self, client, api_key_header):
        response = client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["name"] == "Premium Widget"

    def test_create_sku_unauthorized(self, client, invalid_api_key_header):
        response = client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=invalid_api_key_header,
        )
        assert response.status_code == 401

    def test_create_duplicate_sku(self, client, api_key_header):
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        response = client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Another Widget"},
            headers=api_key_header,
        )
        assert response.status_code == 409


class TestInventoryEndpoint:
    def test_adjust_stock_succeeds(self, client, api_key_header):
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        response = client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers=api_key_header,
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 100

    def test_adjust_stock_nonexistent_sku(self, client, api_key_header):
        response = client.post(
            "/api/inventory/adjust",
            json={"sku": "NONEXISTENT", "quantity": 100},
            headers=api_key_header,
        )
        assert response.status_code == 404

    def test_adjust_stock_unauthorized(self, client, invalid_api_key_header):
        response = client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers=invalid_api_key_header,
        )
        assert response.status_code == 401


class TestReservationEndpoint:
    def test_create_reservation_succeeds(self, client, api_key_header):
        # Setup
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers=api_key_header,
        )

        # Test
        response = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=api_key_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["quantity"] == 10
        assert data["state"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key_header):
        # Setup
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 5},
            headers=api_key_header,
        )

        # Test
        response = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=api_key_header,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client, api_key_header):
        # Setup
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers=api_key_header,
        )

        # First request
        response1 = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=api_key_header,
        )
        assert response1.status_code == 200
        id1 = response1.json()["id"]

        # Retry with same idempotency key
        response2 = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=api_key_header,
        )
        assert response2.status_code == 200
        id2 = response2.json()["id"]

        # Same reservation returned
        assert id1 == id2

    def test_create_reservation_unauthorized(self, client, invalid_api_key_header):
        response = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=invalid_api_key_header,
        )
        assert response.status_code == 401


class TestConfirmReservationEndpoint:
    def test_confirm_reservation_succeeds(self, client, api_key_header):
        # Setup
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers=api_key_header,
        )
        res = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=api_key_header,
        )
        reservation_id = res.json()["id"]

        # Test
        response = client.post(
            f"/api/reservations/{reservation_id}/confirm",
            headers=api_key_header,
        )
        assert response.status_code == 200
        assert response.json()["state"] == "confirmed"

    def test_confirm_nonexistent_reservation(self, client, api_key_header):
        response = client.post(
            "/api/reservations/999/confirm",
            headers=api_key_header,
        )
        assert response.status_code == 404

    def test_confirm_reservation_unauthorized(self, client, invalid_api_key_header):
        response = client.post(
            "/api/reservations/1/confirm",
            headers=invalid_api_key_header,
        )
        assert response.status_code == 401


class TestCancelReservationEndpoint:
    def test_cancel_reservation_succeeds(self, client, api_key_header):
        # Setup
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers=api_key_header,
        )
        res = client.post(
            "/api/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=api_key_header,
        )
        reservation_id = res.json()["id"]

        # Test
        response = client.post(
            f"/api/reservations/{reservation_id}/cancel",
            headers=api_key_header,
        )
        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"

    def test_cancel_nonexistent_reservation(self, client, api_key_header):
        response = client.post(
            "/api/reservations/999/cancel",
            headers=api_key_header,
        )
        assert response.status_code == 404


class TestOrdersEndpoint:
    def test_list_orders_empty(self, client):
        response = client.get("/api/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0

    def test_list_orders_paginated(self, client, api_key_header):
        # Setup
        client.post(
            "/api/skus",
            json={"sku": "WIDGET-001", "name": "Premium Widget"},
            headers=api_key_header,
        )
        client.post(
            "/api/inventory/adjust",
            json={"sku": "WIDGET-001", "quantity": 1000},
            headers=api_key_header,
        )

        # Create and confirm 25 reservations
        for i in range(25):
            res = client.post(
                "/api/reservations",
                json={
                    "sku": "WIDGET-001",
                    "quantity": 1,
                    "idempotency_key": f"key-{i}",
                },
                headers=api_key_header,
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/api/reservations/{reservation_id}/confirm",
                headers=api_key_header,
            )

        # Test pagination
        response1 = client.get("/api/orders?skip=0&limit=20")
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["orders"]) == 20
        assert data1["total"] == 25

        response2 = client.get("/api/orders?skip=20&limit=20")
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 5
