import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture(autouse=True)
def setup_api_key():
    os.environ["COMMERCE_API_KEY"] = "test-api-key"
    yield
    if "COMMERCE_API_KEY" in os.environ:
        del os.environ["COMMERCE_API_KEY"]


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client(temp_db):
    from src.commerce_service import app as app_module
    app_module.repository = Repository(database_url=temp_db)
    app_module.service = CommerceService(app_module.repository)
    return TestClient(app)


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSkuCreation:
    def test_create_sku_with_valid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SKU001"
        assert data["name"] == "Widget A"

    def test_create_sku_without_api_key(self, client):
        response = client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
        )
        assert response.status_code == 401
        assert "API key" in response.json()["detail"]

    def test_create_sku_with_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]


class TestStockAdjustment:
    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity_available"] == 100

    def test_adjust_stock_invalid_sku(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku_id": 999, "quantity": 10},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 400


class TestReservation:
    def test_create_reservation_happy_path(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert len(data["reservations"]) == 1
        assert data["reservations"][0]["quantity"] == 50

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 50},
            headers={"X-API-Key": "test-api-key"},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 100, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        response1 = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        response2 = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["id"] == response2.json()["id"]

    def test_create_reservation_without_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
        )
        assert response.status_code == 401


class TestReservationConfirmation:
    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        reservation_id = res.json()["reservations"][0]["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["reservations"][0]["status"] == "confirmed"

    def test_confirm_reservation_not_found(self, client):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 404

    def test_confirm_reservation_without_api_key(self, client):
        response = client.post("/reservations/1/confirm")
        assert response.status_code == 401


class TestReservationCancellation:
    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        reservation_id = res.json()["reservations"][0]["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert response.json()["reservations"][0]["status"] == "cancelled"

    def test_cancel_reservation_returns_stock(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        reservation_id = res.json()["reservations"][0]["id"]

        client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": "test-api-key"},
        )

        stock_response = client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 0},
            headers={"X-API-Key": "test-api-key"},
        )
        assert stock_response.json()["quantity_available"] == 100

    def test_cancel_reservation_without_api_key(self, client):
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 401


class TestOrderLookup:
    def test_list_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 5000},
            headers={"X-API-Key": "test-api-key"},
        )

        for i in range(15):
            client.post(
                "/reservations",
                json={"sku_id": 1, "quantity": 10, "idempotency_key": f"key{i}"},
                headers={"X-API-Key": "test-api-key"},
            )

        response = client.get(
            "/orders?page=1&page_size=10",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["page_size"] == 10

        response = client.get(
            "/orders?page=2&page_size=10",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5

    def test_get_order_by_id(self, client):
        client.post(
            "/skus",
            json={"code": "SKU001", "name": "Widget A"},
            headers={"X-API-Key": "test-api-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": "test-api-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": "test-api-key"},
        )
        order_id = res.json()["id"]

        response = client.get(
            f"/orders/{order_id}",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["status"] == "pending"

    def test_get_order_not_found(self, client):
        response = client.get(
            "/orders/999",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 404

    def test_list_orders_without_api_key(self, client):
        response = client.get("/orders")
        assert response.status_code == 401
