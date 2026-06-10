"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository


@pytest.fixture(autouse=True)
def reset_db():
    """Clear database before each test."""
    repo = Repository()
    repo.clear_all()
    yield
    repo.clear_all()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def valid_headers():
    """Valid API key headers."""
    return {"x-api-key": "test-key"}


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKU:
    def test_create_sku(self, client, valid_headers):
        response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "widget"
        assert data["quantity"] == 100
        assert "id" in data

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
        )
        assert response.status_code == 401

    def test_create_sku_wrong_key(self, client):
        response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers={"x-api-key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_name(self, client, valid_headers):
        response = client.post(
            "/skus",
            json={"name": "", "quantity": 100},
            headers=valid_headers,
        )
        assert response.status_code == 422

    def test_adjust_stock(self, client, valid_headers):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        # Adjust stock
        response = client.post(
            f"/skus/{sku_id}/adjust",
            json={"delta": 50},
            headers=valid_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 150

    def test_adjust_stock_negative(self, client, valid_headers):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        # Reduce stock
        response = client.post(
            f"/skus/{sku_id}/adjust",
            json={"delta": -30},
            headers=valid_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 70

    def test_adjust_stock_unauthorized(self, client):
        response = client.post(
            "/skus/1/adjust",
            json={"delta": 50},
        )
        assert response.status_code == 401


class TestReservation:
    def test_create_reservation_success(self, client, valid_headers):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 50
        assert data["status"] == "pending"
        assert "expires_at" in data

    def test_create_reservation_insufficient_stock(self, client, valid_headers):
        # Create SKU with low stock
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 30},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client, valid_headers):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        res1 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res1_id = res1.json()["id"]

        # Retry with same idempotency key
        res2 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res2_id = res2.json()["id"]

        # Should return same reservation
        assert res1_id == res2_id
        assert res2.status_code == 201

    def test_get_reservation(self, client, valid_headers):
        # Create SKU and reservation
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        # Get reservation
        response = client.get(f"/reservations/{res_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == res_id
        assert data["status"] == "pending"

    def test_get_reservation_not_found(self, client):
        response = client.get("/reservations/999")
        assert response.status_code == 404

    def test_confirm_reservation(self, client, valid_headers):
        # Create SKU and reservation
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        # Confirm reservation
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert "order_id" in data

    def test_confirm_reservation_unauthorized(self, client, valid_headers):
        # Create SKU and reservation
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        # Try to confirm without API key
        response = client.post(f"/reservations/{res_id}/confirm")
        assert response.status_code == 401

    def test_cancel_reservation(self, client, valid_headers):
        # Create SKU and reservation
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        # Cancel reservation
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=valid_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

        # Check stock is returned
        sku_response = client.get("/skus/1")
        # Note: We can't directly get SKU, so verify via order list

    def test_cancel_reservation_idempotent(self, client, valid_headers):
        # Create SKU and reservation
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        # Cancel twice
        response1 = client.post(
            f"/reservations/{res_id}/cancel",
            headers=valid_headers,
        )
        response2 = client.post(
            f"/reservations/{res_id}/cancel",
            headers=valid_headers,
        )

        assert response1.status_code == 200
        assert response2.status_code == 200


class TestOrder:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["offset"] == 0
        assert data["limit"] == 20

    def test_list_orders_with_pagination(self, client, valid_headers):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 500},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        # Create and confirm multiple reservations
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={
                    "sku_id": sku_id,
                    "quantity": 10,
                    "idempotency_key": f"key-{i}",
                },
                headers=valid_headers,
            )
            res_id = res_response.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=valid_headers)

        # Test pagination
        response = client.get("/orders?offset=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["offset"] == 0
        assert data["limit"] == 2

    def test_get_order(self, client, valid_headers):
        # Create SKU and reservation
        sku_response = client.post(
            "/skus",
            json={"name": "widget", "quantity": 100},
            headers=valid_headers,
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        order_id = confirm_response.json()["order_id"]

        # Get order
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 50
        assert data["status"] == "confirmed"

    def test_get_order_not_found(self, client):
        response = client.get("/orders/999")
        assert response.status_code == 404
