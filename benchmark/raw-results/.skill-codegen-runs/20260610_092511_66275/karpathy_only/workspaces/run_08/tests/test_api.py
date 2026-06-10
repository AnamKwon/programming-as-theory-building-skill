import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.models import ReservationState
from commerce_service.repository import Repository


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    return TestClient(app)


@pytest.fixture
def headers():
    return {"X-API-Key": "test-key"}


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, headers):
        payload = {"id": "SKU-001", "name": "Widget", "initial_stock": 100}
        response = client.post("/skus", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "SKU-001"
        assert data["name"] == "Widget"
        assert data["available_stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        payload = {"id": "SKU-001", "name": "Widget", "initial_stock": 100}
        response = client.post("/skus", json=payload)
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        payload = {"sku_id": "SKU-001", "quantity": 10}
        response = client.post("/stock/adjust", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 110

    def test_adjust_stock_decrease(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        payload = {"sku_id": "SKU-001", "quantity": -30}
        response = client.post("/stock/adjust", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 70


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        payload = {"sku_id": "SKU-001", "quantity": 10}
        response = client.post("/reservations", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU-001"
        assert data["quantity"] == 10
        assert data["state"] == "reserved"
        assert data["expires_at"] is not None
        reservation_id = data["id"]

        sku = client.post("/stock/adjust", json={"sku_id": "SKU-001", "quantity": 0}, headers=headers).json()
        assert sku["available_stock"] == 90
        assert sku["reserved_stock"] == 10

    def test_create_reservation_insufficient_stock(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 5}, headers=headers)

        payload = {"sku_id": "SKU-001", "quantity": 10}
        response = client.post("/reservations", json=payload, headers=headers)
        assert response.status_code == 409
        assert "insufficient" in response.json()["detail"].lower()

    def test_create_reservation_idempotent(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        payload = {"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-001"}
        response1 = client.post("/reservations", json=payload, headers=headers)
        response2 = client.post("/reservations", json=payload, headers=headers)

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_confirm_reservation_success(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        res = client.post("/reservations", json={"sku_id": "SKU-001", "quantity": 10}, headers=headers)
        reservation_id = res.json()["id"]

        response = client.post(f"/reservations/{reservation_id}/confirm", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "confirmed"
        assert data["confirmed_at"] is not None

    def test_confirm_nonexistent_reservation(self, client, headers):
        response = client.post("/reservations/NONEXISTENT/confirm", headers=headers)
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        res = client.post("/reservations", json={"sku_id": "SKU-001", "quantity": 10}, headers=headers)
        reservation_id = res.json()["id"]

        response = client.post(f"/reservations/{reservation_id}/cancel", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "cancelled"

        sku = client.post("/stock/adjust", json={"sku_id": "SKU-001", "quantity": 0}, headers=headers).json()
        assert sku["available_stock"] == 100
        assert sku["reserved_stock"] == 0

    def test_cancel_confirmed_reservation_fails(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        res = client.post("/reservations", json={"sku_id": "SKU-001", "quantity": 10}, headers=headers)
        reservation_id = res.json()["id"]

        client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

        response = client.post(f"/reservations/{reservation_id}/cancel", headers=headers)
        assert response.status_code == 409


class TestOrderListEndpoint:
    def test_list_orders_empty(self, client, headers):
        response = client.get("/orders", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_list_orders_pagination(self, client, headers):
        client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100}, headers=headers)

        for i in range(15):
            client.post("/reservations", json={"sku_id": "SKU-001", "quantity": 1}, headers=headers)

        response = client.get("/orders?page=1&page_size=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["page_size"] == 10

        response = client.get("/orders?page=2&page_size=10", headers=headers)
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 2

    def test_list_orders_requires_api_key(self, client):
        response = client.get("/orders")
        assert response.status_code == 401

    def test_list_orders_invalid_pagination(self, client, headers):
        response = client.get("/orders?page=0", headers=headers)
        assert response.status_code == 422

        response = client.get("/orders?page_size=101", headers=headers)
        assert response.status_code == 422


class TestAuthenticationAndAuthorization:
    def test_missing_api_key_on_post_sku(self, client):
        response = client.post("/skus", json={"id": "SKU-001", "name": "Widget", "initial_stock": 100})
        assert response.status_code == 401

    def test_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_health_check_no_auth(self, client):
        response = client.get("/health")
        assert response.status_code == 200
