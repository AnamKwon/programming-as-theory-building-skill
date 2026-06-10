import pytest
import os
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import init_db, DB_PATH


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key_header():
    return {"X-API-Key": "test-api-key"}


class TestHealthEndpoint:

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoint:

    def test_create_sku_success(self, client, api_key_header):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["initial_stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100}
        )
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]


class TestStockAdjustEndpoint:

    def test_adjust_stock_success(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 50},
            headers=api_key_header
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["updated_stock"] == 150

    def test_adjust_stock_negative(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": -30},
            headers=api_key_header
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_stock"] == 70

    def test_adjust_stock_sku_not_found(self, client, api_key_header):
        response = client.post(
            "/stock/adjust",
            json={"sku": "NON-EXISTENT", "amount": 50},
            headers=api_key_header
        )
        assert response.status_code == 404


class TestReservationEndpoint:

    def test_create_reservation_success(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["quantity"] == 50
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 30},
            headers=api_key_header
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        response1 = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        assert response1.status_code == 201
        data1 = response1.json()

        response2 = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        assert response2.status_code == 201
        data2 = response2.json()

        assert data1["id"] == data2["id"]

        stock_response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 0},
            headers=api_key_header
        )
        assert stock_response.json()["updated_stock"] == 50

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            }
        )
        assert response.status_code == 401


class TestConfirmReservationEndpoint:

    def test_confirm_reservation_success(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=api_key_header
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"

    def test_confirm_non_pending_reservation(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=api_key_header
        )

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=api_key_header
        )
        assert response.status_code == 400

    def test_confirm_missing_api_key(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        reservation_id = res_response.json()["id"]

        response = client.post(f"/reservations/{reservation_id}/confirm")
        assert response.status_code == 401


class TestCancelReservationEndpoint:

    def test_cancel_reservation_success(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=api_key_header
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

        stock_response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 0},
            headers=api_key_header
        )
        assert stock_response.json()["updated_stock"] == 100

    def test_cancel_non_pending_reservation(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=api_key_header
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1"
            },
            headers=api_key_header
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=api_key_header
        )

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=api_key_header
        )
        assert response.status_code == 400


class TestOrdersEndpoint:

    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 10

    def test_get_orders_pagination(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 1000},
            headers=api_key_header
        )

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU-001",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-{i}"
                },
                headers=api_key_header
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=api_key_header
            )

        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1

        response = client.get("/orders?page=2&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 15
        assert data["page"] == 2

    def test_get_orders_default_pagination(self, client, api_key_header):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 1000},
            headers=api_key_header
        )

        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU-001",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-{i}"
                },
                headers=api_key_header
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=api_key_header
            )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 10
