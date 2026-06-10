import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def temp_db():
    """Create a temporary database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def client(temp_db):
    """Create a test client with a temporary database."""
    from commerce_service import app as app_module

    app_module.repository = Repository(temp_db)
    app_module.service = Service(app_module.repository)

    return TestClient(app)


def get_auth_headers():
    return {"X-API-Key": "test-api-key"}


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["database"] == "ok"


class TestSKU:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget", "price": 29.99, "stock": 100},
            headers=get_auth_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Widget"
        assert data["price"] == 29.99
        assert data["current_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget", "price": 29.99, "stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget", "price": 29.99, "stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Widget", "price": 29.99, "stock": 100},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        response = client.post(
            f"/skus/{sku_id}/stock",
            json={"quantity": 50},
            headers=get_auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["current_stock"] == 150

    def test_adjust_stock_not_found(self, client):
        response = client.post(
            "/skus/nonexistent/stock",
            json={"quantity": 10},
            headers=get_auth_headers(),
        )
        assert response.status_code == 404


class TestReservation:
    def test_create_reservation(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Item", "price": 9.99, "stock": 100},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
            headers=get_auth_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 10
        assert data["status"] == "RESERVED"

    def test_create_reservation_insufficient_stock(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Item", "price": 9.99, "stock": 5},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-2"},
            headers=get_auth_headers(),
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_unauthorized(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": "sku-1", "quantity": 10, "idempotency_key": "key-3"},
        )
        assert response.status_code == 401

    def test_create_reservation_idempotency(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Item", "price": 9.99, "stock": 100},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        response1 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-4"},
            headers=get_auth_headers(),
        )
        reservation_id_1 = response1.json()["reservation_id"]

        response2 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 20, "idempotency_key": "key-4"},
            headers=get_auth_headers(),
        )
        reservation_id_2 = response2.json()["reservation_id"]

        assert reservation_id_1 == reservation_id_2
        assert response2.json()["quantity"] == 10


class TestConfirmation:
    def test_confirm_reservation(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Item", "price": 9.99, "stock": 100},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-5"},
            headers=get_auth_headers(),
        )
        reservation_id = res_response.json()["reservation_id"]

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=get_auth_headers(),
        )
        assert confirm_response.status_code == 200
        order_id = confirm_response.json()["order_id"]

        order_response = client.get(f"/orders/{order_id}")
        assert order_response.status_code == 200
        assert order_response.json()["status"] == "CONFIRMED"
        assert len(order_response.json()["items"]) == 1

    def test_confirm_reservation_unauthorized(self, client):
        response = client.post(
            "/reservations/nonexistent/confirm",
            json={},
        )
        assert response.status_code == 401


class TestCancellation:
    def test_cancel_reservation(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Item", "price": 9.99, "stock": 100},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-6"},
            headers=get_auth_headers(),
        )
        reservation_id = res_response.json()["reservation_id"]

        cancel_response = client.delete(
            f"/reservations/{reservation_id}",
            headers=get_auth_headers(),
        )
        assert cancel_response.status_code == 204

    def test_cancel_reservation_not_found(self, client):
        response = client.delete(
            "/reservations/nonexistent",
            headers=get_auth_headers(),
        )
        assert response.status_code == 404


class TestOrderListing:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0

    def test_list_orders_with_pagination(self, client):
        sku_response = client.post(
            "/skus",
            json={"name": "Item", "price": 9.99, "stock": 200},
            headers=get_auth_headers(),
        )
        sku_id = sku_response.json()["sku_id"]

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={"sku_id": sku_id, "quantity": 5, "idempotency_key": f"key-{i}"},
                headers=get_auth_headers(),
            )
            reservation_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={},
                headers=get_auth_headers(),
            )

        response1 = client.get("/orders?skip=0&limit=10")
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["orders"]) == 10
        assert data1["total"] == 15

        response2 = client.get("/orders?skip=10&limit=10")
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 5
        assert data2["total"] == 15

    def test_get_order_not_found(self, client):
        response = client.get("/orders/nonexistent")
        assert response.status_code == 404
