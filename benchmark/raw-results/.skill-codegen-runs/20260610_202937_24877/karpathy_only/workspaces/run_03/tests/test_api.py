import pytest
import time
from fastapi.testclient import TestClient
from src.commerce_service.app import app, repo, service
from src.commerce_service.security import VALID_API_KEY


@pytest.fixture(autouse=True)
def cleanup():
    yield
    repo.clear_all()


client = TestClient(app)
HEADERS = {"X-API-Key": VALID_API_KEY}


class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku(self):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_api_key(self):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
        )
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_create_sku_invalid_api_key(self):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]


class TestStockAdjustment:
    def test_adjust_stock_increase(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 50},
            headers=HEADERS,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 25},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 75

    def test_adjust_stock_decrease(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 50},
            headers=HEADERS,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": -20},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 30

    def test_adjust_stock_nonexistent_sku(self):
        response = client.post(
            "/stock/adjust",
            json={"sku": "NONEXISTENT", "amount": 10},
            headers=HEADERS,
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation_success(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "PENDING"
        assert data["quantity"] == 30

    def test_create_reservation_insufficient_stock(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 20},
            headers=HEADERS,
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_reservation_idempotency(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )

        data1 = response1.json()
        data2 = response2.json()
        assert data1["id"] == data2["id"]
        assert response1.status_code == 201
        assert response2.status_code == 201


class TestConfirmEndpoint:
    def test_confirm_reservation(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"

    def test_confirm_expired_reservation(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        time.sleep(0.35)

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Reservation expired"

    def test_confirm_nonpending_reservation(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 400


class TestCancelEndpoint:
    def test_cancel_reservation(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_restores_stock(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/cancel",
            headers=HEADERS,
        )

        sku_data = repo.get_sku_by_name("SKU-001")
        assert sku_data["available_stock"] == 100


class TestOrdersEndpoint:
    def test_get_orders_pagination(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 1000},
            headers=HEADERS,
        )

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU-001",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-{i}",
                },
                headers=HEADERS,
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers=HEADERS,
            )

        response = client.get("/orders?page=1&size=10", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 15

    def test_get_orders_second_page(self):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 1000},
            headers=HEADERS,
        )

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU-001",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-{i}",
                },
                headers=HEADERS,
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers=HEADERS,
            )

        response = client.get("/orders?page=2&size=10", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["page"] == 2


class TestAuthenticationRequirements:
    def test_adjust_stock_requires_auth(self):
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 10},
        )
        assert response.status_code == 401

    def test_create_reservation_requires_auth(self):
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 10,
                "idempotency_key": "test",
            },
        )
        assert response.status_code == 401

    def test_confirm_requires_auth(self):
        response = client.post("/reservations/1/confirm")
        assert response.status_code == 401

    def test_cancel_requires_auth(self):
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 401

    def test_get_orders_requires_auth(self):
        response = client.get("/orders")
        assert response.status_code == 401
