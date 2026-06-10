import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, repository, service
from commerce_service.repository import Repository

API_KEY = "test-key-123"
INVALID_KEY = "invalid-key"


@pytest.fixture
def temp_db():
    _, db_path = tempfile.mkstemp(suffix=".db")
    yield f"sqlite:///{db_path}"
    os.unlink(db_path)


@pytest.fixture(autouse=True)
def reset_service(temp_db):
    new_repo = Repository(database_url=temp_db)
    service.repo = new_repo


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKU:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget", "description": "A widget"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        assert response.json()["id"] == "SKU-001"

    def test_create_sku_without_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
        )
        assert response.status_code == 401

    def test_create_sku_with_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": INVALID_KEY},
        )
        assert response.status_code == 401

    def test_get_sku(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        response = client.get("/skus/SKU-001")
        assert response.status_code == 200
        assert response.json()["name"] == "Widget"

    def test_get_nonexistent_sku(self, client):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404


class TestStock:
    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 204

    def test_adjust_stock_without_api_key(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
        )
        assert response.status_code == 401

    def test_adjust_stock_nonexistent_sku(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "NONEXISTENT", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 404


class TestReservation:
    def test_create_reservation(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        assert response.json()["quantity"] == 10
        assert response.json()["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 5},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )

        key = "idempotency-key-1"
        res1 = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": key},
            headers={"X-API-Key": API_KEY},
        )
        res2 = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": key},
            headers={"X-API-Key": API_KEY},
        )

        assert res1.json()["id"] == res2.json()["id"]

    def test_create_reservation_without_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
        )
        assert response.status_code == 401

    def test_get_reservation(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        response = client.get(f"/reservations/{res_id}")
        assert response.status_code == 200
        assert response.json()["id"] == res_id

    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        response = client.delete(
            f"/reservations/{res_id}",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_reservation_without_api_key(self, client):
        response = client.delete(
            "/reservations/some-id",
        )
        assert response.status_code == 401


class TestOrder:
    def test_confirm_reservation_creates_order(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        response = client.patch(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["reservation_id"] == res_id

    def test_confirm_reservation_without_api_key(self, client):
        response = client.patch(
            "/reservations/some-id/confirm",
        )
        assert response.status_code == 401

    def test_get_order(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]
        order = client.patch(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )
        order_id = order.json()["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["id"] == order_id

    def test_list_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )

        for _ in range(15):
            res = client.post(
                "/reservations",
                json={"sku_id": "SKU-001", "quantity": 1},
                headers={"X-API-Key": API_KEY},
            )
            res_id = res.json()["id"]
            client.patch(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": API_KEY},
            )

        response = client.get("/orders?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["skip"] == 0
        assert data["limit"] == 10

        response = client.get("/orders?skip=10&limit=10")
        data = response.json()
        assert len(data["items"]) == 5

    def test_confirm_reservation_idempotent(self, client):
        client.post(
            "/skus",
            json={"id": "SKU-001", "name": "Widget"},
            headers={"X-API-Key": API_KEY},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "SKU-001", "quantity_delta": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        key = "order-key-1"
        order1 = client.patch(
            f"/reservations/{res_id}/confirm?idempotency_key={key}",
            headers={"X-API-Key": API_KEY},
        )
        order2 = client.patch(
            f"/reservations/{res_id}/confirm?idempotency_key={key}",
            headers={"X-API-Key": API_KEY},
        )

        assert order1.json()["id"] == order2.json()["id"]
