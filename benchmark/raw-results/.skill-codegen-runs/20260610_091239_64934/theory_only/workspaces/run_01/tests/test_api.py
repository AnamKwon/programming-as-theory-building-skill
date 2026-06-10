import pytest
from fastapi.testclient import TestClient

from commerce_service import app as app_module
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def client():
    app_module._repo = Repository()
    app_module._service = CommerceService(app_module._repo)
    yield TestClient(app_module.app)
    app_module._repo = None
    app_module._service = None


VALID_API_KEY = "test-api-key-123"
INVALID_API_KEY = "invalid-key"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku_requires_auth(self, client):
        response = client.post(
            "/skus", json={"sku_id": "PROD-001", "initial_stock": 100}
        )
        assert response.status_code == 403

    def test_create_sku_invalid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "PROD-001", "initial_stock": 100},
            headers={"X-API-Key": INVALID_API_KEY},
        )
        assert response.status_code == 403

    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "PROD-001", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "PROD-001"
        assert data["available_stock"] == 100
        assert data["reserved_stock"] == 0

    def test_get_sku(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-002", "initial_stock": 50},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.get("/skus/PROD-002")
        assert response.status_code == 200
        assert response.json()["available_stock"] == 50

    def test_get_nonexistent_sku(self, client):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404

    def test_adjust_stock_requires_auth(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-003", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post("/skus/PROD-003/adjust-stock", json={"adjustment": 50})
        assert response.status_code == 403

    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-004", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/skus/PROD-004/adjust-stock",
            json={"adjustment": 50},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 150


class TestReservationEndpoints:
    def test_create_reservation_requires_auth(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-005", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-005",
                "quantity": 20,
                "idempotency_key": "idempotent-1",
                "ttl_seconds": 300,
            },
        )
        assert response.status_code == 403

    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-006", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-006",
                "quantity": 20,
                "idempotency_key": "idempotent-2",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "PROD-006"
        assert data["quantity"] == 20
        assert data["state"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-007", "initial_stock": 50},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-007",
                "quantity": 100,
                "idempotency_key": "idempotent-3",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 409

    def test_get_reservation(self, client):
        create_sku_response = client.post(
            "/skus",
            json={"sku_id": "PROD-008", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        create_res_response = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-008",
                "quantity": 20,
                "idempotency_key": "idempotent-4",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = create_res_response.json()["reservation_id"]

        response = client.get(f"/reservations/{res_id}")
        assert response.status_code == 200
        assert response.json()["state"] == "pending"

    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-009", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-009",
                "quantity": 20,
                "idempotency_key": "idempotent-5",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = create_res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={"reservation_id": res_id, "idempotency_key": "idempotent-6"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "confirmed"

    def test_confirm_reservation_requires_auth(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-010", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-010",
                "quantity": 20,
                "idempotency_key": "idempotent-7",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = create_res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={"reservation_id": res_id, "idempotency_key": "idempotent-8"},
        )
        assert response.status_code == 403

    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-011", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-011",
                "quantity": 20,
                "idempotency_key": "idempotent-9",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = create_res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            json={"reservation_id": res_id},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"


class TestOrderEndpoints:
    def test_create_order_requires_auth(self, client):
        response = client.post(
            "/orders",
            json={"reservation_ids": ["RES-001"], "idempotency_key": "idempotent-10"},
        )
        assert response.status_code == 403

    def test_create_order_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-012", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-012",
                "quantity": 20,
                "idempotency_key": "idempotent-11",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = create_res.json()["reservation_id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            json={"reservation_id": res_id, "idempotency_key": "idempotent-12"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        response = client.post(
            "/orders",
            json={"reservation_ids": [res_id], "idempotency_key": "idempotent-13"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert res_id in data["reservation_ids"]
        assert data["state"] == "pending"

    def test_get_order(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-013", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-013",
                "quantity": 20,
                "idempotency_key": "idempotent-14",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = create_res.json()["reservation_id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            json={"reservation_id": res_id, "idempotency_key": "idempotent-15"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        create_order = client.post(
            "/orders",
            json={"reservation_ids": [res_id], "idempotency_key": "idempotent-16"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        order_id = create_order.json()["order_id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["order_id"] == order_id

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders/NONEXISTENT")
        assert response.status_code == 404

    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["orders"]) == 0

    def test_list_orders_with_pagination(self, client):
        client.post(
            "/skus",
            json={"sku_id": "PROD-014", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )

        for i in range(15):
            create_res = client.post(
                "/reservations",
                json={
                    "sku_id": "PROD-014",
                    "quantity": 1,
                    "idempotency_key": f"idempotent-{i}",
                    "ttl_seconds": 300,
                },
                headers={"X-API-Key": VALID_API_KEY},
            )
            res_id = create_res.json()["reservation_id"]

            client.post(
                f"/reservations/{res_id}/confirm",
                json={"reservation_id": res_id, "idempotency_key": f"idempotent-confirm-{i}"},
                headers={"X-API-Key": VALID_API_KEY},
            )

            client.post(
                "/orders",
                json={"reservation_ids": [res_id], "idempotency_key": f"idempotent-order-{i}"},
                headers={"X-API-Key": VALID_API_KEY},
            )

        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["page_size"] == 10

        response = client.get("/orders?page=2&page_size=10")
        data = response.json()
        assert len(data["orders"]) == 5
