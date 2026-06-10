import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # Replace the app's repo with temp one
    from commerce_service import app as app_module
    app_module.repo = Repository(db_path=path)
    app_module.service = app_module.CommerceService(app_module.repo)
    yield path
    os.unlink(path)


@pytest.fixture
def client(temp_db):
    return TestClient(app)


VALID_KEY = "commerce-secret-key-12345"
HEADERS = {"X-API-Key": VALID_KEY}


class TestHealthCheck:
    def test_health_check_success(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoint:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-A", "name": "Widget A"},
            headers=HEADERS
        )
        assert response.status_code == 200
        assert response.json()["sku"] == "WIDGET-A"

    def test_create_sku_without_api_key_raises_401(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-A", "name": "Widget A"}
        )
        assert response.status_code == 401

    def test_create_sku_with_invalid_key_raises_403(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-A", "name": "Widget A"},
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 403


class TestStockEndpoint:
    def test_adjust_stock_success(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        response = client.post(
            "/stock",
            json={"sku": "WIDGET-A", "quantity": 100},
            headers=HEADERS
        )
        assert response.status_code == 200
        assert response.json()["available_quantity"] == 100

    def test_adjust_stock_without_auth_raises_401(self, client):
        response = client.post(
            "/stock",
            json={"sku": "WIDGET-A", "quantity": 100}
        )
        assert response.status_code == 401


class TestReservationEndpoint:
    def test_create_reservation_success(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 100}, headers=HEADERS)

        response = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1",
                "ttl_seconds": 3600
            },
            headers=HEADERS
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "WIDGET-A"
        assert data["quantity"] == 10
        assert data["state"] == "pending"

    def test_create_reservation_insufficient_stock_raises_409(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 5}, headers=HEADERS)

        response = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        )
        assert response.status_code == 409

    def test_idempotent_reservation(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 100}, headers=HEADERS)

        response1 = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["id"] == response2.json()["id"]

    def test_cancel_reservation_success(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        ).json()

        response = client.post(
            f"/reservations/{res['id']}/cancel",
            headers=HEADERS
        )
        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"

    def test_confirm_reservation_creates_order(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        ).json()

        response = client.post(
            f"/reservations/{res['id']}/confirm",
            headers=HEADERS
        )
        assert response.status_code == 200
        order = response.json()
        assert order["state"] == "confirmed"
        assert order["quantity"] == 10


class TestOrderEndpoint:
    def test_get_order_success(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        ).json()
        order_resp = client.post(
            f"/reservations/{res['id']}/confirm",
            headers=HEADERS
        ).json()

        response = client.get(f"/orders/{order_resp['id']}")
        assert response.status_code == 200
        assert response.json()["state"] == "confirmed"

    def test_get_nonexistent_order_raises_404(self, client):
        response = client.get("/orders/nonexistent-id")
        assert response.status_code == 404

    def test_list_orders_pagination(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 1000}, headers=HEADERS)

        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku": "WIDGET-A",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-{i}"
                },
                headers=HEADERS
            ).json()
            client.post(f"/reservations/{res['id']}/confirm", headers=HEADERS)

        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1

        response2 = client.get("/orders?page=2&page_size=10")
        data2 = response2.json()
        assert len(data2["orders"]) == 5

    def test_list_orders_default_pagination(self, client):
        client.post("/skus", json={"sku": "WIDGET-A", "name": "Widget A"}, headers=HEADERS)
        client.post("/stock", json={"sku": "WIDGET-A", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-A",
                "quantity": 10,
                "idempotency_key": "idempotency-1"
            },
            headers=HEADERS
        ).json()
        client.post(f"/reservations/{res['id']}/confirm", headers=HEADERS)

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
