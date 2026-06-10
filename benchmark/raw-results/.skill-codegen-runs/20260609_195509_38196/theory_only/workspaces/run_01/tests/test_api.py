import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    return "test-key"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku(self, client, api_key):
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "SKU001"
        assert data["name"] == "Widget"
        assert data["quantity_on_hand"] == 100

    def test_create_sku_without_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
        )
        assert response.status_code == 403

    def test_create_sku_with_wrong_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_get_sku(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.get("/skus/SKU001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "SKU001"

    def test_get_sku_not_found(self, client):
        response = client.get("/skus/missing")
        assert response.status_code == 404

    def test_adjust_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "SKU001", "delta": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["quantity_on_hand"] == 150

    def test_adjust_stock_below_zero(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 50},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "SKU001", "delta": -100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 50
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 50},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 400

    def test_create_reservation_idempotency(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        resp1 = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key1"},
            headers={"X-API-Key": api_key},
        )
        resp2 = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": api_key},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["id"] == resp2.json()["id"]
        assert resp1.json()["quantity"] == 50

    def test_create_reservation_without_api_key(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
        )
        assert response.status_code == 403

    def test_cancel_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "canceled"


class TestConfirmEndpoint:
    def test_confirm_reservation_happy_path(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 50
        assert data["reservation_id"] == res_id

    def test_confirm_reservation_idempotency(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        resp1 = client.post(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "confirm1"},
            headers={"X-API-Key": api_key},
        )
        resp2 = client.post(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": "confirm1"},
            headers={"X-API-Key": api_key},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["id"] == resp2.json()["id"]

    def test_confirm_reservation_without_api_key(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["has_next"] is False

    def test_list_orders_with_data(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": api_key},
        )

        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["orders"]) == 1

    def test_list_orders_pagination(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 1000},
            headers={"X-API-Key": api_key},
        )
        for i in range(25):
            res_resp = client.post(
                "/reservations",
                json={"sku_id": "SKU001", "quantity": 10},
                headers={"X-API-Key": api_key},
            )
            res_id = res_resp.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                json={},
                headers={"X-API-Key": api_key},
            )

        resp1 = client.get("/orders?page=1&page_size=10")
        resp2 = client.get("/orders?page=2&page_size=10")
        resp3 = client.get("/orders?page=3&page_size=10")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 200

        data1 = resp1.json()
        data2 = resp2.json()
        data3 = resp3.json()

        assert len(data1["orders"]) == 10
        assert len(data2["orders"]) == 10
        assert len(data3["orders"]) == 5
        assert data1["has_next"] is True
        assert data2["has_next"] is True
        assert data3["has_next"] is False

    def test_list_orders_invalid_page(self, client):
        response = client.get("/orders?page=0")
        assert response.status_code == 400

    def test_list_orders_invalid_page_size(self, client):
        response = client.get("/orders?page_size=1000")
        assert response.status_code == 400

    def test_get_order(self, client, api_key):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "quantity_on_hand": 100},
            headers={"X-API-Key": api_key},
        )
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 50},
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["id"]
        order_resp = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": api_key},
        )
        order_id = order_resp.json()["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id

    def test_get_order_not_found(self, client):
        response = client.get("/orders/missing")
        assert response.status_code == 404
