import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import Base, SessionLocal, app, get_db


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal()
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture(autouse=True)
def set_api_key():
    os.environ["COMMERCE_API_KEY"] = "test-key"
    yield
    if "COMMERCE_API_KEY" in os.environ:
        del os.environ["COMMERCE_API_KEY"]


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["name"] == "Widget"
        assert data["available_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_wrong_key(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/skus/SKU001/adjust-stock",
            json={"quantity": 50},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 150

    def test_adjust_nonexistent_sku(self, client):
        response = client.post(
            "/skus/NONEXISTENT/adjust-stock",
            json={"quantity": 10},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 10
        assert data["status"] == "pending"
        assert data["reservation_id"]

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 50},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 409

    def test_idempotent_reservation(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res1 = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key123"},
            headers={"X-API-Key": "test-key"},
        )
        res2 = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "key123"},
            headers={"X-API-Key": "test-key"},
        )

        assert res1.status_code == 201
        assert res2.status_code == 201
        assert res1.json()["reservation_id"] == res2.json()["reservation_id"]

    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_resp.json()["reservation_id"]

        confirm_resp = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert confirm_resp.status_code == 200
        data = confirm_resp.json()
        assert data["order_id"]
        assert data["status"] == "pending"
        assert len(data["items"]) == 1

    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 30},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_resp.json()["reservation_id"]

        cancel_resp = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    def test_cancel_nonpending_reservation(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_resp.json()["reservation_id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )

        cancel_resp = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert cancel_resp.status_code == 409


class TestOrderEndpoints:
    def test_list_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 1000},
            headers={"X-API-Key": "test-key"},
        )

        for _ in range(25):
            res_resp = client.post(
                "/reservations",
                json={"sku_id": "SKU001", "quantity": 10},
                headers={"X-API-Key": "test-key"},
            )
            res_id = res_resp.json()["reservation_id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": "test-key"},
            )

        page1 = client.get("/orders?page=1&page_size=10")
        assert page1.status_code == 200
        data = page1.json()
        assert len(data["items"]) == 10
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["pages"] == 3

        page3 = client.get("/orders?page=3&page_size=10")
        assert page3.status_code == 200
        assert len(page3.json()["items"]) == 5

    def test_get_order(self, client):
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_resp.json()["reservation_id"]

        order_resp = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        order_id = order_resp.json()["order_id"]

        get_resp = client.get(f"/orders/{order_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["order_id"] == order_id
        assert data["status"] == "pending"
        assert len(data["items"]) == 1
