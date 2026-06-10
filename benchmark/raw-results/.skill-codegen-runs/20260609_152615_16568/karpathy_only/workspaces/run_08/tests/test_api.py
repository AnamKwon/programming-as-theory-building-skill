import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, repo, service


@pytest.fixture
def client():
    # Use in-memory DB for tests
    global repo, service
    from commerce_service.repository import Repository
    from commerce_service.service import CommerceService

    test_repo = Repository(db_path=":memory:")
    test_service = CommerceService(test_repo)

    # Monkey patch the global repo and service
    import commerce_service.app
    commerce_service.app.repo = test_repo
    commerce_service.app.service = test_service

    yield TestClient(app)


@pytest.fixture
def api_key():
    return "demo-api-key"


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_create_sku_duplicate(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Another", "initial_stock": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409

    def test_adjust_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "delta": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["quantity"] == 30
        assert data["state"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 50},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 100,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_idempotent_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res1 = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        res2 = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        assert res1.json()["id"] == res2.json()["id"]

    def test_cancel_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert "cancelled" in response.json()["message"].lower()


class TestOrderEndpoints:
    def test_confirm_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "confirm-key-1"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "reserved"
        assert data["sku"] == "SKU-001"

    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orders_pagination(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 1000},
            headers={"X-API-Key": api_key},
        )
        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku": "SKU-001",
                    "quantity": 10,
                    "idempotency_key": f"key-{i}",
                    "ttl_seconds": 300,
                },
                headers={"X-API-Key": api_key},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                json={"idempotency_key": f"confirm-key-{i}"},
                headers={"X-API-Key": api_key},
            )

        page1 = client.get("/orders?offset=0&limit=10")
        assert page1.status_code == 200
        assert len(page1.json()["items"]) == 10
        assert page1.json()["total"] == 15

        page2 = client.get("/orders?offset=10&limit=10")
        assert page2.status_code == 200
        assert len(page2.json()["items"]) == 5

    def test_get_order(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 30,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]

        order_res = client.post(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "confirm-key-1"},
            headers={"X-API-Key": api_key},
        )
        order_id = order_res.json()["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["id"] == order_id

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders/nonexistent")
        assert response.status_code == 404


class TestErrorHandling:
    def test_create_sku_validation_error(self, client, api_key):
        response = client.post(
            "/skus",
            json={"sku": "", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 422

    def test_create_reservation_validation_error(self, client, api_key):
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 0,
                "idempotency_key": "key-1",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 422
