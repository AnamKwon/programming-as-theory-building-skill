import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app, repo, service

client = TestClient(app)
API_KEY = "test-key-123"


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the database before each test."""
    global repo, service
    from src.commerce_service.repository import Repository
    from src.commerce_service.service import CommerceService

    repo = Repository(db_path=":memory:")
    service = CommerceService(repo)
    app.dependency_overrides.clear()


class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSKUEndpoints:
    def test_create_sku_success(self):
        response = client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PROD-001"
        assert data["stock"] == 100
        assert data["available"] == 100

    def test_create_sku_unauthorized(self):
        response = client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_key(self):
        response = client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_get_sku_success(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.get("/skus/PROD-001")
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "PROD-001"
        assert data["stock"] == 100

    def test_get_nonexistent_sku(self):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404

    def test_adjust_stock_success(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/skus/PROD-001/adjust-stock",
            json={"adjustment": 50},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stock"] == 150

    def test_adjust_stock_unauthorized(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/skus/PROD-001/adjust-stock",
            json={"adjustment": 50},
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation_success(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 10,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PROD-001"
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 150,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409

    def test_create_reservation_unauthorized(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 10,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
        )
        assert response.status_code == 401

    def test_confirm_reservation_success(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 10,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        response = client.patch(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "idempotent-1"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert "order_id" in data

    def test_confirm_reservation_idempotent(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 10,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        response1 = client.patch(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "idempotent-1"},
            headers={"X-API-Key": API_KEY},
        )
        response2 = client.patch(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "idempotent-1"},
            headers={"X-API-Key": API_KEY},
        )
        assert response1.json()["order_id"] == response2.json()["order_id"]

    def test_cancel_reservation_success(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 10,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        response = client.delete(
            f"/reservations/{res_id}",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 204

        sku = client.get("/skus/PROD-001")
        assert sku.json()["reserved"] == 0

    def test_cancel_confirmed_reservation_fails(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 10,
                "idempotency_key": "idempotent-1",
                "customer_id": "customer-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        res_id = res.json()["id"]

        client.patch(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "idempotent-1"},
            headers={"X-API-Key": API_KEY},
        )

        response = client.delete(
            f"/reservations/{res_id}",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409


class TestOrderEndpoints:
    def test_list_orders_empty(self):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_orders_with_pagination(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )

        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku": "PROD-001",
                    "quantity": 1,
                    "idempotency_key": f"idempotent-{i}",
                    "customer_id": f"customer-{i}",
                },
                headers={"X-API-Key": API_KEY},
            )
            res_id = res.json()["id"]
            client.patch(
                f"/reservations/{res_id}/confirm",
                json={"idempotency_key": f"idempotent-{i}"},
                headers={"X-API-Key": API_KEY},
            )

        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 15
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["total_pages"] == 2

        response = client.get("/orders?page=2&page_size=10")
        data = response.json()
        assert len(data["items"]) == 5

    def test_list_orders_custom_page_size(self):
        client.post(
            "/skus",
            json={"sku": "PROD-001", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )

        for i in range(5):
            res = client.post(
                "/reservations",
                json={
                    "sku": "PROD-001",
                    "quantity": 1,
                    "idempotency_key": f"idempotent-{i}",
                    "customer_id": f"customer-{i}",
                },
                headers={"X-API-Key": API_KEY},
            )
            res_id = res.json()["id"]
            client.patch(
                f"/reservations/{res_id}/confirm",
                json={"idempotency_key": f"idempotent-{i}"},
                headers={"X-API-Key": API_KEY},
            )

        response = client.get("/orders?page=1&page_size=3")
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 3
        assert data["total_pages"] == 2
