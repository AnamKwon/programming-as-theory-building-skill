import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(test_engine, db_session):
    from src.commerce_service.app import app, get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    return "commerce-secret-key-12345"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        response = client.post(
            "/skus",
            json={"sku_id": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "TEST-001"
        assert data["available_stock"] == 100

    def test_create_sku_no_auth(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "TEST-002", "initial_stock": 50},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "TEST-003", "initial_stock": 50},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock_success(self, client, api_key):
        client.post(
            "/skus",
            json={"sku_id": "TEST-004", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.put(
            "/skus/TEST-004/stock",
            json={"adjustment": 25},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 125

    def test_adjust_stock_not_found(self, client, api_key):
        response = client.put(
            "/skus/NONEXISTENT/stock",
            json={"adjustment": 10},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, api_key):
        client.post(
            "/skus",
            json={"sku_id": "RES-001", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "RES-001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "RES-001"
        assert data["quantity"] == 50
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"sku_id": "RES-002", "initial_stock": 30},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "RES-002", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent(self, client, api_key):
        client.post(
            "/skus",
            json={"sku_id": "RES-003", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "RES-003",
                "quantity": 30,
                "idempotency_key": "key-001",
            },
            headers={"X-API-Key": api_key},
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "RES-003",
                "quantity": 30,
                "idempotency_key": "key-001",
            },
            headers={"X-API-Key": api_key},
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_confirm_reservation_success(self, client, api_key):
        client.post(
            "/skus",
            json={"sku_id": "CONF-001", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res_response = client.post(
            "/reservations",
            json={"sku_id": "CONF-001", "quantity": 40},
            headers={"X-API-Key": api_key},
        )
        res_id = res_response.json()["reservation_id"]

        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert "order_id" in data
        assert data["quantity"] == 40

    def test_confirm_reservation_not_found(self, client, api_key):
        response = client.post(
            "/reservations/NONEXISTENT/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client, api_key):
        client.post(
            "/skus",
            json={"sku_id": "CAN-001", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res_response = client.post(
            "/reservations",
            json={"sku_id": "CAN-001", "quantity": 30},
            headers={"X-API-Key": api_key},
        )
        res_id = res_response.json()["reservation_id"]

        cancel_response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

    def test_cancel_reservation_not_found(self, client, api_key):
        response = client.post(
            "/reservations/NONEXISTENT/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_list_orders_empty(self, client, api_key):
        response = client.get(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    def test_list_orders_with_pagination(self, client, api_key):
        # Create SKU
        client.post(
            "/skus",
            json={"sku_id": "ORD-001", "initial_stock": 500},
            headers={"X-API-Key": api_key},
        )

        # Create and confirm 25 orders
        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={"sku_id": "ORD-001", "quantity": 1},
                headers={"X-API-Key": api_key},
            )
            res_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        # Get first page
        response1 = client.get(
            "/orders?page=1&page_size=10",
            headers={"X-API-Key": api_key},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["orders"]) == 10
        assert data1["total"] == 25
        assert data1["page"] == 1
        assert data1["page_size"] == 10

        # Get second page
        response2 = client.get(
            "/orders?page=2&page_size=10",
            headers={"X-API-Key": api_key},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 10
        assert data2["page"] == 2

    def test_list_orders_no_auth(self, client):
        response = client.get("/orders")
        assert response.status_code == 401

    def test_list_orders_invalid_key(self, client):
        response = client.get(
            "/orders",
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403
