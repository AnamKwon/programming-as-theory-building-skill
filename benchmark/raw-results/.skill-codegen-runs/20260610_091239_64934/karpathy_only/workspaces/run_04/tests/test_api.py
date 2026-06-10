import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture(autouse=True)
def setup_db(temp_db, monkeypatch):
    monkeypatch.setattr("src.commerce_service.app.repo", Repository(temp_db))
    app.dependency_overrides.clear()
    repo = Repository(temp_db)
    repo.init_db()
    monkeypatch.setattr("src.commerce_service.app.repo", repo)
    monkeypatch.setattr("src.commerce_service.app.service.repo", repo)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    return "test-api-key"


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        response = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test Product",
                "initial_stock": 100,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "PROD001"
        assert data["stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={
                "sku_code": "PROD001",
                "name": "Test Product",
                "initial_stock": 100,
            },
        )
        assert response.status_code == 403

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            headers={"X-API-Key": "invalid-key"},
            json={
                "sku_code": "PROD001",
                "name": "Test Product",
                "initial_stock": 100,
            },
        )
        assert response.status_code == 403

    def test_create_sku_duplicate(self, client, api_key):
        client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test Product",
                "initial_stock": 100,
            },
        )
        response = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Another",
                "initial_stock": 50,
            },
        )
        assert response.status_code == 409

    def test_adjust_stock_success(self, client, api_key):
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test",
                "initial_stock": 100,
            },
        )
        sku_id = sku_response.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/stock",
            headers={"X-API-Key": api_key},
            json={"quantity": 50},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150

    def test_adjust_stock_unauthorized(self, client):
        response = client.post(
            "/skus/1/stock",
            json={"quantity": 50},
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    def test_create_order(self, client, api_key):
        response = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"

    def test_get_order(self, client, api_key):
        create_resp = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        order_id = create_resp.json()["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["id"] == order_id

    def test_get_order_not_found(self, client):
        response = client.get("/orders/999")
        assert response.status_code == 404

    def test_list_orders_pagination(self, client, api_key):
        for i in range(5):
            client.post("/orders", headers={"X-API-Key": api_key})

        response = client.get("/orders?offset=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["orders"]) == 2
        assert data["offset"] == 0
        assert data["limit"] == 2

    def test_list_orders_invalid_pagination(self, client):
        response = client.get("/orders?offset=-1&limit=20")
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, api_key):
        sku_resp = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test",
                "initial_stock": 100,
            },
        )
        sku_id = sku_resp.json()["id"]

        order_resp = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["id"]

        response = client.post(
            f"/orders/{order_id}/reservations",
            headers={"X-API-Key": api_key},
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "key-001",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 30
        assert data["status"] == "reserved"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        sku_resp = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test",
                "initial_stock": 50,
            },
        )
        sku_id = sku_resp.json()["id"]

        order_resp = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["id"]

        response = client.post(
            f"/orders/{order_id}/reservations",
            headers={"X-API-Key": api_key},
            json={
                "sku_id": sku_id,
                "quantity": 100,
                "idempotency_key": "key-001",
            },
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client, api_key):
        sku_resp = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test",
                "initial_stock": 100,
            },
        )
        sku_id = sku_resp.json()["id"]

        order_resp = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["id"]

        req_body = {
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "key-001",
        }

        resp1 = client.post(
            f"/orders/{order_id}/reservations",
            headers={"X-API-Key": api_key},
            json=req_body,
        )
        resp2 = client.post(
            f"/orders/{order_id}/reservations",
            headers={"X-API-Key": api_key},
            json=req_body,
        )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] == resp2.json()["id"]

        sku = client.get(f"/skus/{sku_id}").json()
        assert sku["stock"] == 70

    def test_confirm_reservation_success(self, client, api_key):
        sku_resp = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test",
                "initial_stock": 100,
            },
        )
        sku_id = sku_resp.json()["id"]

        order_resp = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["id"]

        res_resp = client.post(
            f"/orders/{order_id}/reservations",
            headers={"X-API-Key": api_key},
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "key-001",
            },
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/orders/{order_id}/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_cancel_reservation_success(self, client, api_key):
        sku_resp = client.post(
            "/skus",
            headers={"X-API-Key": api_key},
            json={
                "sku_code": "PROD001",
                "name": "Test",
                "initial_stock": 100,
            },
        )
        sku_id = sku_resp.json()["id"]

        order_resp = client.post(
            "/orders",
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["id"]

        res_resp = client.post(
            f"/orders/{order_id}/reservations",
            headers={"X-API-Key": api_key},
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "key-001",
            },
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/orders/{order_id}/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        sku = client.get(f"/skus/{sku_id}").json()
        assert sku["stock"] == 100

    def test_reservation_unauthorized(self, client):
        response = client.post(
            "/orders/1/reservations",
            json={
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": "key-001",
            },
        )
        assert response.status_code == 403
