import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from commerce_service.app import app, get_db
from commerce_service.models import Base

DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku(self):
        response = client.post(
            "/skus",
            json={"code": "SKU-001", "stock": 100},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SKU-001"
        assert data["stock"] == 100
        assert data["reserved_count"] == 0

    def test_create_sku_without_api_key(self):
        response = client.post(
            "/skus",
            json={"code": "SKU-001", "stock": 100},
        )
        assert response.status_code == 401

    def test_create_duplicate_sku(self):
        client.post("/skus", json={"code": "SKU-001", "stock": 100}, headers=HEADERS)
        response = client.post(
            "/skus",
            json={"code": "SKU-001", "stock": 50},
            headers=HEADERS,
        )
        assert response.status_code == 409

    def test_adjust_stock(self):
        sku_response = client.post(
            "/skus", json={"code": "SKU-001", "stock": 100}, headers=HEADERS
        )
        sku_id = sku_response.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/adjust-stock",
            json={"quantity": 50},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150


class TestReservationEndpoints:
    def setup_method(self):
        sku_response = client.post(
            "/skus", json={"code": "SKU-001", "stock": 100}, headers=HEADERS
        )
        self.sku_id = sku_response.json()["id"]

    def test_create_reservation(self):
        response = client.post(
            "/reservations",
            json={
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self):
        response = client.post(
            "/reservations",
            json={
                "sku_id": self.sku_id,
                "quantity": 150,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_idempotent_reservation(self):
        res1 = client.post(
            "/reservations",
            json={
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res2 = client.post(
            "/reservations",
            json={
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        assert res1.json()["id"] == res2.json()["id"]

    def test_confirm_reservation(self):
        res = client.post(
            "/reservations",
            json={
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == res_id

    def test_cancel_reservation(self):
        res = client.post(
            "/reservations",
            json={
                "sku_id": self.sku_id,
                "quantity": 10,
                "idempotency_key": "idempotency-1",
            },
            headers=HEADERS,
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrderEndpoints:
    def setup_method(self):
        sku_response = client.post(
            "/skus", json={"code": "SKU-001", "stock": 1000}, headers=HEADERS
        )
        self.sku_id = sku_response.json()["id"]

    def test_list_orders_empty(self):
        response = client.get("/orders", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    def test_list_orders_with_pagination(self):
        for i in range(25):
            res = client.post(
                "/reservations",
                json={
                    "sku_id": self.sku_id,
                    "quantity": 1,
                    "idempotency_key": f"idempotency-{i}",
                },
                headers=HEADERS,
            )
            res_id = res.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)

        response = client.get("/orders?skip=0&limit=10", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["items"]) == 10
        assert data["skip"] == 0
        assert data["limit"] == 10

        response2 = client.get("/orders?skip=20&limit=10", headers=HEADERS)
        data2 = response2.json()
        assert len(data2["items"]) == 5

    def test_orders_without_api_key(self):
        response = client.get("/orders")
        assert response.status_code == 401
