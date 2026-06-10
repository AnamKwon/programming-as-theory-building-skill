import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Database


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    os.unlink(path)


@pytest.fixture
def client(temp_db, monkeypatch):
    # Patch the global db instance in app
    monkeypatch.setattr("commerce_service.app.db", temp_db)
    monkeypatch.setattr(
        "commerce_service.app.service",
        __import__("commerce_service.service", fromlist=["CommerceService"]).CommerceService(
            temp_db
        ),
    )
    return TestClient(app)


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku_requires_api_key(self, client):
        payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        response = client.post("/skus", json=payload)
        assert response.status_code == 401

    def test_create_sku_with_api_key(self, client):
        payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        response = client.post(
            "/skus", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["stock_quantity"] == 100

    def test_create_sku_duplicate_fails(self, client):
        payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        client.post("/skus", json=payload, headers={"X-API-Key": "test-api-key-123"})
        response = client.post(
            "/skus", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        assert response.status_code == 409

    def test_adjust_stock_requires_api_key(self, client):
        # First create the SKU
        payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        client.post("/skus", json=payload, headers={"X-API-Key": "test-api-key-123"})

        response = client.post("/skus/SKU001/adjust-stock", json={"quantity_delta": 10})
        assert response.status_code == 401

    def test_adjust_stock_with_api_key(self, client):
        # Create SKU
        payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        client.post("/skus", json=payload, headers={"X-API-Key": "test-api-key-123"})

        response = client.post(
            "/skus/SKU001/adjust-stock",
            json={"quantity_delta": 50},
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert response.status_code == 200
        assert response.json()["stock_quantity"] == 150


class TestReservationEndpoints:
    @pytest.fixture
    def setup_sku(self, client):
        payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        client.post("/skus", json=payload, headers={"X-API-Key": "test-api-key-123"})

    def test_create_reservation_requires_api_key(self, client, setup_sku):
        payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        response = client.post("/reservations", json=payload)
        assert response.status_code == 401

    def test_create_reservation(self, client, setup_sku):
        payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        response = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_idempotent(self, client, setup_sku):
        payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        response1 = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        response2 = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )

        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_create_reservation_insufficient_stock(self, client, setup_sku):
        payload = {"sku_id": "SKU001", "quantity": 200, "idempotency_key": "key-1"}
        response = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_confirm_reservation(self, client, setup_sku):
        # Create reservation
        payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        res = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        reservation_id = res.json()["reservation_id"]

        # Confirm it
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_cancel_reservation(self, client, setup_sku):
        # Create reservation
        payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        res = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        reservation_id = res.json()["reservation_id"]

        # Cancel it
        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_unauthorized_mutation_fails(self, client, setup_sku):
        payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        res = client.post(
            "/reservations", json=payload, headers={"X-API-Key": "test-api-key-123"}
        )
        reservation_id = res.json()["reservation_id"]

        # Try to confirm with invalid API key
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    @pytest.fixture
    def setup_orders(self, client):
        # Create SKU and reservation, then confirm it to create an order
        sku_payload = {"sku_id": "SKU001", "name": "Widget", "initial_stock": 100}
        client.post("/skus", json=sku_payload, headers={"X-API-Key": "test-api-key-123"})

        res_payload = {"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key-1"}
        res = client.post(
            "/reservations",
            json=res_payload,
            headers={"X-API-Key": "test-api-key-123"},
        )
        reservation_id = res.json()["reservation_id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": "test-api-key-123"},
        )

    def test_list_orders(self, client, setup_orders):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 1
        assert data["total"] == 1

    def test_list_orders_pagination(self, client, setup_orders):
        # Create more orders
        sku_payload = {"sku_id": "SKU002", "name": "Gadget", "initial_stock": 100}
        client.post("/skus", json=sku_payload, headers={"X-API-Key": "test-api-key-123"})

        for i in range(1, 5):
            res_payload = {
                "sku_id": "SKU002",
                "quantity": 5,
                "idempotency_key": f"key-{i+1}",
            }
            res = client.post(
                "/reservations",
                json=res_payload,
                headers={"X-API-Key": "test-api-key-123"},
            )
            reservation_id = res.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={},
                headers={"X-API-Key": "test-api-key-123"},
            )

        # Test pagination
        response1 = client.get("/orders?limit=2&offset=0")
        assert len(response1.json()["orders"]) == 2
        assert response1.json()["total"] == 5

        response2 = client.get("/orders?limit=2&offset=2")
        assert len(response2.json()["orders"]) == 2

    def test_get_order(self, client, setup_orders):
        response = client.get("/orders")
        order_id = response.json()["orders"][0]["order_id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["order_id"] == order_id

    def test_get_nonexistent_order_fails(self, client):
        response = client.get("/orders/nonexistent")
        assert response.status_code == 404
