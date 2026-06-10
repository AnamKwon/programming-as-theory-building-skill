import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app, db, service
import os


@pytest.fixture(autouse=True)
def setup_and_teardown():
    test_db = "test_commerce.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    yield
    if os.path.exists(test_db):
        os.remove(test_db)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_token():
    return "test-api-token-123"


class TestHealthEndpoint:
    def test_health_check_success(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_without_token(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU123", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_with_invalid_token(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU123", "initial_stock": 100},
            headers={"X-API-Token": "invalid-token"},
        )
        assert response.status_code == 401

    def test_create_sku_success(self, client, api_token):
        response = client.post(
            "/skus",
            json={"sku": "SKU123", "initial_stock": 100},
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU123"
        assert data["available_stock"] == 100

    def test_adjust_stock_success(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU456", "initial_stock": 50},
            headers={"X-API-Token": api_token},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU456", "amount": 25},
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU456"
        assert data["available_stock"] == 75

    def test_adjust_stock_negative(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU789", "initial_stock": 50},
            headers={"X-API-Token": api_token},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU789", "amount": -20},
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 30


class TestReservationEndpoints:
    def test_reservation_without_token(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU123",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
        )
        assert response.status_code == 401

    def test_reservation_insufficient_stock(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU999", "initial_stock": 5},
            headers={"X-API-Token": api_token},
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "SKU999",
                "quantity": 10,
                "idempotency_key": "key-insufficient",
            },
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_reservation_success(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Token": api_token},
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "key-res-1",
            },
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 25
        assert data["status"] == "PENDING"
        assert data["idempotency_key"] == "key-res-1"

    def test_reservation_idempotency(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU002", "initial_stock": 100},
            headers={"X-API-Token": api_token},
        )

        response1 = client.post(
            "/reservations",
            json={
                "sku": "SKU002",
                "quantity": 30,
                "idempotency_key": "idempotent-key",
            },
            headers={"X-API-Token": api_token},
        )
        assert response1.status_code == 201
        data1 = response1.json()

        response2 = client.post(
            "/reservations",
            json={
                "sku": "SKU002",
                "quantity": 30,
                "idempotency_key": "idempotent-key",
            },
            headers={"X-API-Token": api_token},
        )
        assert response2.status_code == 201
        data2 = response2.json()

        assert data1["id"] == data2["id"]
        assert data1["quantity"] == data2["quantity"]

    def test_confirm_reservation_success(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU003", "initial_stock": 50},
            headers={"X-API-Token": api_token},
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "SKU003",
                "quantity": 15,
                "idempotency_key": "key-confirm",
            },
            headers={"X-API-Token": api_token},
        )
        res_id = res.json()["id"]

        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": api_token},
        )
        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert data["status"] == "CONFIRMED"

    def test_confirm_reservation_not_pending(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU004", "initial_stock": 50},
            headers={"X-API-Token": api_token},
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "SKU004",
                "quantity": 15,
                "idempotency_key": "key-confirm-2",
            },
            headers={"X-API-Token": api_token},
        )
        res_id = res.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": api_token},
        )

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 400
        assert "not pending" in response.json()["detail"]

    def test_cancel_reservation_success(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU005", "initial_stock": 50},
            headers={"X-API-Token": api_token},
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "SKU005",
                "quantity": 20,
                "idempotency_key": "key-cancel",
            },
            headers={"X-API-Token": api_token},
        )
        res_id = res.json()["id"]

        cancel_response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Token": api_token},
        )
        assert cancel_response.status_code == 200
        data = cancel_response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_reservation_restores_stock(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU006", "initial_stock": 100},
            headers={"X-API-Token": api_token},
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "SKU006",
                "quantity": 40,
                "idempotency_key": "key-cancel-stock",
            },
            headers={"X-API-Token": api_token},
        )
        res_id = res.json()["id"]

        client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Token": api_token},
        )

        check_stock = client.post(
            "/stock/adjust",
            json={"sku": "SKU006", "amount": 0},
            headers={"X-API-Token": api_token},
        )
        assert check_stock.json()["available_stock"] == 100


class TestOrderEndpoints:
    def test_list_orders_without_token(self, client):
        response = client.get("/orders")
        assert response.status_code == 401

    def test_list_orders_empty(self, client, api_token):
        response = client.get(
            "/orders",
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 10

    def test_list_orders_with_pagination(self, client, api_token):
        client.post(
            "/skus",
            json={"sku": "SKU010", "initial_stock": 500},
            headers={"X-API-Token": api_token},
        )

        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku": "SKU010",
                    "quantity": 10,
                    "idempotency_key": f"key-order-{i}",
                },
                headers={"X-API-Token": api_token},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Token": api_token},
            )

        response = client.get(
            "/orders?page=1&size=10",
            headers={"X-API-Token": api_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["size"] == 10

        response2 = client.get(
            "/orders?page=2&size=10",
            headers={"X-API-Token": api_token},
        )
        data2 = response2.json()
        assert len(data2["items"]) == 5
        assert data2["page"] == 2


class TestHappyPath:
    def test_complete_workflow(self, client, api_token):
        sku_response = client.post(
            "/skus",
            json={"sku": "WORKFLOW-SKU", "initial_stock": 100},
            headers={"X-API-Token": api_token},
        )
        assert sku_response.status_code == 201

        res_response = client.post(
            "/reservations",
            json={
                "sku": "WORKFLOW-SKU",
                "quantity": 30,
                "idempotency_key": "workflow-key",
            },
            headers={"X-API-Token": api_token},
        )
        assert res_response.status_code == 201
        res_id = res_response.json()["id"]

        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": api_token},
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "CONFIRMED"

        orders_response = client.get(
            "/orders",
            headers={"X-API-Token": api_token},
        )
        assert orders_response.status_code == 200
        orders = orders_response.json()
        assert len(orders["items"]) == 1
        assert orders["items"][0]["reservation_id"] == res_id
