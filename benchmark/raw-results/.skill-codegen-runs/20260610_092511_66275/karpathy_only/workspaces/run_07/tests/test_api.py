import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, service, repo
from commerce_service.models import OrderState


@pytest.fixture(autouse=True)
def reset_db():
    repo.clear_all()
    yield
    repo.clear_all()


client = TestClient(app)
VALID_API_KEY = "sk-test-key-12345"


class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self):
        response = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "WIDGET-001"
        assert data["quantity"] == 100

    def test_create_sku_unauthorized(self):
        response = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_key(self):
        response = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock_increase(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 50},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/adjust-stock",
            json={"delta": 25},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 75

    def test_adjust_stock_decrease(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 50},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/adjust-stock",
            json={"delta": -10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 40

    def test_adjust_stock_insufficient(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 50},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/adjust-stock",
            json={"delta": -100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400

    def test_adjust_stock_not_found(self):
        response = client.post(
            "/skus/999/adjust-stock",
            json={"delta": 10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "res-key-1",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_unauthorized(self):
        response = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": "res-key-1",
            },
        )
        assert response.status_code == 403

    def test_create_reservation_insufficient_stock(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 20,
                "idempotency_key": "res-key-2",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 409

    def test_create_reservation_sku_not_found(self):
        response = client.post(
            "/reservations",
            json={
                "sku_id": 999,
                "quantity": 10,
                "idempotency_key": "res-key-3",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 404

    def test_create_reservation_idempotent(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        key = "idempotent-res-key"
        res1 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": key},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res2 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": key},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert res1.json()["id"] == res2.json()["id"]

    def test_cancel_reservation_success(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        res_resp = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "cancel-key"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_reservation_unauthorized(self):
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 403


class TestOrderEndpoints:
    def test_confirm_reservation_success(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        res_resp = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "order-key-1"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "confirmed"
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 10

    def test_confirm_reservation_unauthorized(self):
        response = client.post(
            "/reservations/1/confirm",
            json={},
        )
        assert response.status_code == 403

    def test_confirm_reservation_not_found(self):
        response = client.post(
            "/reservations/999/confirm",
            json={},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 404

    def test_list_orders_pagination(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 1000},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        for i in range(25):
            res_resp = client.post(
                "/reservations",
                json={
                    "sku_id": sku_id,
                    "quantity": 1,
                    "idempotency_key": f"order-key-{i}",
                },
                headers={"X-API-Key": VALID_API_KEY},
            )
            res_id = res_resp.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                json={},
                headers={"X-API-Key": VALID_API_KEY},
            )

        response = client.get("/orders?offset=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 25
        assert data["offset"] == 0
        assert data["limit"] == 10

        response2 = client.get("/orders?offset=20&limit=10")
        assert len(response2.json()["items"]) == 5

    def test_list_orders_default_pagination(self):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 0
        assert data["limit"] == 10

    def test_get_order_success(self):
        sku_resp = client.post(
            "/skus",
            json={"sku_code": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        sku_id = sku_resp.json()["id"]

        res_resp = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 5, "idempotency_key": "get-order-key"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = res_resp.json()["id"]

        order_resp = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": VALID_API_KEY},
        )
        order_id = order_resp.json()["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["state"] == "confirmed"

    def test_get_order_not_found(self):
        response = client.get("/orders/999")
        assert response.status_code == 404


class TestErrorHandling:
    def test_invalid_pagination_limit(self):
        response = client.get("/orders?limit=200")
        assert response.status_code == 422

    def test_negative_pagination_offset(self):
        response = client.get("/orders?offset=-1")
        assert response.status_code == 422
