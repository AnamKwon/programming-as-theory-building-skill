import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401


class TestStockAdjustment:
    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST001", "amount": 25},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "TEST001"
        assert data["new_stock"] == 125

    def test_adjust_stock_missing_api_key(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST001", "amount": 25},
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST001"
        assert data["quantity"] == 25
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 10},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 20, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Insufficient stock" in data["detail"]

    def test_create_reservation_idempotency(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res1 = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        assert res1.status_code == 201
        first_id = res1.json()["id"]

        res2 = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        assert res2.status_code == 201
        second_data = res2.json()
        assert second_data["id"] == first_id
        assert second_data["quantity"] == 25

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
        )
        assert response.status_code == 401

    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"

    def test_confirm_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations/1/confirm",
        )
        assert response.status_code == 401

    def test_confirm_reservation_not_found(self, client):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_reservation_restores_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res.json()["id"]

        client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )

        res2 = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 30, "idempotency_key": "key-2"},
            headers={"X-API-Key": "test-key"},
        )
        assert res2.status_code == 201

    def test_cancel_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations/1/cancel",
        )
        assert response.status_code == 401


class TestOrderEndpoints:
    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 0
        assert len(data["orders"]) == 0

    def test_get_orders_with_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 1000},
            headers={"X-API-Key": "test-key"},
        )

        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku": "TEST001", "quantity": 1, "idempotency_key": f"key-{i}"},
                headers={"X-API-Key": "test-key"},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": "test-key"},
            )

        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 15
        assert len(data["orders"]) == 10

        response = client.get("/orders?page=2&size=10")
        data = response.json()
        assert data["page"] == 2
        assert len(data["orders"]) == 5

    def test_get_orders_default_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 1000},
            headers={"X-API-Key": "test-key"},
        )

        for i in range(25):
            res = client.post(
                "/reservations",
                json={"sku": "TEST001", "quantity": 1, "idempotency_key": f"key-{i}"},
                headers={"X-API-Key": "test-key"},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": "test-key"},
            )

        response = client.get("/orders")
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 25
        assert len(data["orders"]) == 10


class TestExpiration:
    def test_confirm_reservation_expired(self, client):
        from datetime import datetime
        from commerce_service.app import db

        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST001", "quantity": 25, "idempotency_key": "key-1"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res.json()["id"]

        old_time = datetime.utcfromtimestamp(
            datetime.utcnow().timestamp() - 400
        ).isoformat()
        db.execute_update(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res_id),
        )

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "expired" in data["detail"].lower()


class TestCompleteWorkflow:
    def test_complete_flow_through_api(self, client):
        sku_res = client.post(
            "/skus",
            json={"sku": "WIDGET", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert sku_res.status_code == 201

        res = client.post(
            "/reservations",
            json={"sku": "WIDGET", "quantity": 50, "idempotency_key": "order-123"},
            headers={"X-API-Key": "test-key"},
        )
        assert res.status_code == 201
        res_id = res.json()["id"]

        confirm_res = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert confirm_res.status_code == 200

        orders_res = client.get("/orders")
        assert orders_res.status_code == 200
        orders_data = orders_res.json()
        assert orders_data["total"] == 1
        assert orders_data["orders"][0]["reservation_id"] == res_id
