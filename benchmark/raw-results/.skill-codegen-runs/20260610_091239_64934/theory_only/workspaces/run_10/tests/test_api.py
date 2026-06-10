import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_session
from commerce_service.models import Base

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_session():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_session] = override_get_session

client = TestClient(app)

VALID_API_KEY = {"X-API-Key": "dev-key-001"}
INVALID_API_KEY = {"X-API-Key": "invalid-key"}


class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku(self):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU-001", "stock": 100},
            headers=VALID_API_KEY,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU-001"
        assert data["total_stock"] == 100
        assert data["available_stock"] == 100

    def test_create_sku_missing_auth(self):
        response = client.post("/skus", json={"sku_id": "SKU-001", "stock": 100})
        assert response.status_code == 403

    def test_create_sku_invalid_auth(self):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU-001", "stock": 100},
            headers=INVALID_API_KEY,
        )
        assert response.status_code == 403

    def test_adjust_stock(self):
        client.post(
            "/skus",
            json={"sku_id": "SKU-002", "stock": 100},
            headers=VALID_API_KEY,
        )
        response = client.post(
            "/skus/SKU-002/adjust",
            json={"delta": 50},
            headers=VALID_API_KEY,
        )
        assert response.status_code == 200
        assert response.json()["total_stock"] == 150

    def test_adjust_stock_negative(self):
        client.post(
            "/skus",
            json={"sku_id": "SKU-003", "stock": 100},
            headers=VALID_API_KEY,
        )
        response = client.post(
            "/skus/SKU-003/adjust",
            json={"delta": -30},
            headers=VALID_API_KEY,
        )
        assert response.status_code == 200
        assert response.json()["total_stock"] == 70

    def test_adjust_nonexistent_sku(self):
        response = client.post(
            "/skus/SKU-999/adjust",
            json={"delta": 10},
            headers=VALID_API_KEY,
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def setup_method(self):
        client.post(
            "/skus",
            json={"sku_id": "SKU-RES", "stock": 200},
            headers=VALID_API_KEY,
        )

    def test_create_reservation(self):
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 50},
            headers=VALID_API_KEY,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU-RES"
        assert data["quantity"] == 50
        assert data["status"] == "active"

    def test_create_reservation_insufficient_stock(self):
        response = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 300},
            headers=VALID_API_KEY,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self):
        idempotency_key = "test-key-123"
        response1 = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 50, "idempotency_key": idempotency_key},
            headers=VALID_API_KEY,
        )
        response2 = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 999, "idempotency_key": idempotency_key},
            headers=VALID_API_KEY,
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]
        assert response2.json()["quantity"] == 50

    def test_confirm_reservation(self):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 50},
            headers=VALID_API_KEY,
        )
        reservation_id = res_response.json()["reservation_id"]

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=VALID_API_KEY,
        )
        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert data["status"] == "confirmed"
        assert data["quantity"] == 50

    def test_confirm_reservation_missing_auth(self):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 50},
            headers=VALID_API_KEY,
        )
        reservation_id = res_response.json()["reservation_id"]

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
        )
        assert confirm_response.status_code == 403

    def test_cancel_reservation(self):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 50},
            headers=VALID_API_KEY,
        )
        reservation_id = res_response.json()["reservation_id"]

        cancel_response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=VALID_API_KEY,
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"

    def test_cancel_already_cancelled_is_idempotent(self):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU-RES", "quantity": 50},
            headers=VALID_API_KEY,
        )
        reservation_id = res_response.json()["reservation_id"]

        client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=VALID_API_KEY,
        )
        second_cancel = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=VALID_API_KEY,
        )
        assert second_cancel.status_code == 200


class TestOrderEndpoints:
    def setup_method(self):
        client.post(
            "/skus",
            json={"sku_id": "SKU-ORD", "stock": 500},
            headers=VALID_API_KEY,
        )

    def test_list_orders_empty(self):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["orders"]) == 0
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_orders_with_pagination(self):
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku_id": "SKU-ORD", "quantity": 20},
                headers=VALID_API_KEY,
            )
            reservation_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={},
                headers=VALID_API_KEY,
            )

        response = client.get("/orders?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["orders"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_get_order(self):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "SKU-ORD", "quantity": 30},
            headers=VALID_API_KEY,
        )
        reservation_id = res_response.json()["reservation_id"]

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=VALID_API_KEY,
        )
        order_id = confirm_response.json()["order_id"]

        get_response = client.get(f"/orders/{order_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "confirmed"
        assert data["quantity"] == 30

    def test_get_nonexistent_order(self):
        response = client.get("/orders/ORDER-999")
        assert response.status_code == 404
