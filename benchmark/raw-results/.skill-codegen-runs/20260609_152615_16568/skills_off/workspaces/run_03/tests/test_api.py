import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, repo, service


@pytest.fixture(autouse=True)
def reset_repo():
    global repo, service
    from commerce_service.repository import Repository
    from commerce_service.service import Service

    repo.__dict__.clear()
    repo.__init__(":memory:")
    service.__dict__.clear()
    service.__init__(repo)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    return "test-api-key-123"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKU:
    def test_create_sku(self, client, api_key):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["quantity"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
        )
        assert response.status_code == 401

    def test_adjust_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/skus/WIDGET-001/adjust-stock",
            json={"delta": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 150

    def test_adjust_stock_unauthorized(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/skus/WIDGET-001/adjust-stock",
            json={"delta": 50},
        )
        assert response.status_code == 401


class TestReservation:
    def test_create_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 30,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["quantity"] == 30
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 100,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent_retry(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        response1 = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 30,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )

        response2 = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 30,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_confirm_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        res_resp = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 30,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        reservation_id = res_resp.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "WIDGET-001"

    def test_cancel_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        res_resp = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 30,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        reservation_id = res_resp.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrder:
    def test_get_order(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        res_resp = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 30,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        reservation_id = res_resp.json()["reservation_id"]

        order_resp = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["order_id"]

        response = client.get(
            f"/orders/{order_id}",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "confirmed"

    def test_list_orders(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )

        for i in range(5):
            res_resp = client.post(
                "/reservations",
                json={
                    "sku": "WIDGET-001",
                    "quantity": 10,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": api_key},
            )
            reservation_id = res_resp.json()["reservation_id"]

            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        response = client.get(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["next_cursor"] is None

    def test_list_orders_pagination(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 1000},
            headers={"X-API-Key": api_key},
        )

        for i in range(30):
            res_resp = client.post(
                "/reservations",
                json={
                    "sku": "WIDGET-001",
                    "quantity": 1,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": api_key},
            )
            reservation_id = res_resp.json()["reservation_id"]

            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        response1 = client.get(
            "/orders?limit=20",
            headers={"X-API-Key": api_key},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["orders"]) == 20
        assert data1["next_cursor"] is not None

        response2 = client.get(
            f"/orders?cursor={data1['next_cursor']}&limit=20",
            headers={"X-API-Key": api_key},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 10
        assert data2["next_cursor"] is None

    def test_list_orders_unauthorized(self, client):
        response = client.get("/orders")
        assert response.status_code == 401

    def test_list_orders_invalid_limit(self, client, api_key):
        response = client.get(
            "/orders?limit=200",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 400


class TestSecurity:
    def test_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
        )
        assert response.status_code == 401
