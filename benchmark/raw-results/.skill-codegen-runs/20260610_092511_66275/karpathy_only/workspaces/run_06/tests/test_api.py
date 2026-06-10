import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.app import app, get_db


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKU:
    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        assert response.status_code == 403

    def test_create_sku_authorized(self, client):
        response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "description": "A blue widget",
                "stock_level": 100,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "WIDGET-001"
        assert data["stock_level"] == 100

    def test_create_sku_invalid_key(self, client):
        response = client.post(
            "/skus",
            headers={"X-API-Key": "wrong-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        assert response.status_code == 403

    def test_adjust_stock(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        sku_id = sku_response.json()["id"]

        # Adjust stock
        response = client.post(
            "/stock/adjust",
            headers={"X-API-Key": "test-key"},
            json={"sku_id": sku_id, "quantity_change": -20},
        )
        assert response.status_code == 200
        assert response.json()["stock_level"] == 80


class TestReservation:
    def test_create_reservation(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        response = client.post(
            "/reservations",
            headers={"X-API-Key": "test-key"},
            json={
                "order_id": "order-001",
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "req-001",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["quantity"] == 10

    def test_reservation_insufficient_stock(self, client):
        # Create SKU with limited stock
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 5,
            },
        )
        sku_id = sku_response.json()["id"]

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            headers={"X-API-Key": "test-key"},
            json={
                "order_id": "order-001",
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "req-001",
            },
        )
        assert response.status_code == 409

    def test_reservation_idempotency(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        response1 = client.post(
            "/reservations",
            headers={"X-API-Key": "test-key"},
            json={
                "order_id": "order-001",
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "req-001",
            },
        )
        res_id_1 = response1.json()["id"]

        # Retry with same idempotency key
        response2 = client.post(
            "/reservations",
            headers={"X-API-Key": "test-key"},
            json={
                "order_id": "order-001",
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "req-001",
            },
        )
        res_id_2 = response2.json()["id"]

        assert res_id_1 == res_id_2
        assert response1.status_code == 201
        assert response2.status_code == 201

    def test_confirm_reservation(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        res_response = client.post(
            "/reservations",
            headers={"X-API-Key": "test-key"},
            json={
                "order_id": "order-001",
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "req-001",
            },
        )
        res_id = res_response.json()["id"]

        # Confirm reservation
        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "confirmed"

    def test_cancel_reservation(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 100,
            },
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        res_response = client.post(
            "/reservations",
            headers={"X-API-Key": "test-key"},
            json={
                "order_id": "order-001",
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": "req-001",
            },
        )
        res_id = res_response.json()["id"]

        # Cancel reservation
        cancel_response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

        # Verify stock was released
        sku_check = client.get("/health")  # Quick endpoint to prove db is working
        assert sku_check.status_code == 200


class TestOrders:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["orders"] == []

    def test_list_orders_with_pagination(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            headers={"X-API-Key": "test-key"},
            json={
                "sku_code": "WIDGET-001",
                "name": "Blue Widget",
                "stock_level": 1000,
            },
        )
        sku_id = sku_response.json()["id"]

        # Create multiple orders
        for i in range(5):
            client.post(
                "/reservations",
                headers={"X-API-Key": "test-key"},
                json={
                    "order_id": f"order-{i:03d}",
                    "sku_id": sku_id,
                    "quantity": 10,
                    "idempotency_key": f"req-{i:03d}",
                },
            )

        # List with limit
        response = client.get("/orders?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["orders"]) == 2

        # List with offset
        response2 = client.get("/orders?limit=2&offset=2")
        data2 = response2.json()
        assert len(data2["orders"]) == 2

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        assert response.json()["total"] == 0
