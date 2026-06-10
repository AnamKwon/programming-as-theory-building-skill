import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    os.environ["API_KEY"] = "test-key-123"
    with TestClient(app) as client:
        yield client
    del app.dependency_overrides[get_db]


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKU:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "laptop"
        assert data["stock"] == 10

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_create_duplicate_sku_fails(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 5},
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 400

    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/skus/1/stock",
            json={"quantity_delta": 5},
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stock"] == 15

    def test_adjust_stock_insufficient_fails(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/skus/1/stock",
            json={"quantity_delta": -15},
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 400

    def test_adjust_stock_nonexistent_sku_fails(self, client):
        response = client.post(
            "/skus/999/stock",
            json={"quantity_delta": 5},
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 404


class TestReservation:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == 1
        assert data["quantity"] == 5
        assert data["state"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 3},
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 400

    def test_create_reservation_idempotent(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        assert response1.json()["id"] == response2.json()["id"]

    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/reservations/1/confirm",
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "confirmed"

    def test_confirm_nonexistent_reservation_fails(self, client):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/reservations/1/cancel",
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"

    def test_cancel_confirmed_reservation_fails(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        client.post(
            "/reservations/1/confirm",
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.post(
            "/reservations/1/cancel",
            headers={"X-API-Key": "test-key-123"},
        )
        assert response.status_code == 400


class TestOrder:
    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["next_cursor"] is None

    def test_get_orders_success(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 5,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": "test-key-123"},
        )
        client.post(
            "/reservations/1/confirm",
            headers={"X-API-Key": "test-key-123"},
        )
        response = client.get("/orders")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["quantity"] == 5

    def test_get_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"name": "laptop", "initial_stock": 100},
            headers={"X-API-Key": "test-key-123"},
        )
        for i in range(15):
            client.post(
                "/reservations",
                json={
                    "sku_id": 1,
                    "quantity": 1,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": "test-key-123"},
            )
            client.post(
                f"/reservations/{i + 1}/confirm",
                headers={"X-API-Key": "test-key-123"},
            )

        response1 = client.get("/orders?limit=10")
        assert response1.status_code == 200
        assert len(response1.json()["items"]) == 10
        assert response1.json()["next_cursor"] is not None

        cursor = response1.json()["next_cursor"]
        response2 = client.get(f"/orders?limit=10&cursor={cursor}")
        assert response2.status_code == 200
        assert len(response2.json()["items"]) == 5
        assert response2.json()["next_cursor"] is None

    def test_get_orders_limit_validation(self, client):
        response = client.get("/orders?limit=200")
        assert response.status_code == 200
        assert response.json()["items"] == []
