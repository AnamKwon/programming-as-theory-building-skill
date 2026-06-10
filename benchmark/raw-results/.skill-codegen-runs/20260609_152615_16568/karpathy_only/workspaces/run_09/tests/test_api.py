import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
API_KEY = "secret-key"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


class TestHealthCheck:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSKUEndpoints:
    def test_create_sku(self):
        response = client.post("/skus", json={"sku_code": "SKU001", "description": "Test"}, headers=HEADERS)
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "SKU001"
        assert data["description"] == "Test"

    def test_create_sku_without_api_key(self):
        response = client.post("/skus", json={"sku_code": "SKU001", "description": "Test"})
        assert response.status_code == 403

    def test_create_duplicate_sku(self):
        client.post("/skus", json={"sku_code": "SKU002", "description": "Test"}, headers=HEADERS)
        response = client.post("/skus", json={"sku_code": "SKU002", "description": "Duplicate"}, headers=HEADERS)
        assert response.status_code == 409

    def test_adjust_stock(self):
        client.post("/skus", json={"sku_code": "SKU003", "description": "Test"}, headers=HEADERS)
        response = client.post("/skus/SKU003/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 100
        assert data["reserved_quantity"] == 0

    def test_adjust_stock_nonexistent_sku(self):
        response = client.post("/skus/NONEXISTENT/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self):
        client.post("/skus", json={"sku_code": "SKU004", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU004/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        response = client.post(
            "/reservations",
            json={"sku_code": "SKU004", "quantity": 10, "idempotency_key": "idempotency-1"},
            headers=HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "SKU004"
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self):
        client.post("/skus", json={"sku_code": "SKU005", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU005/adjust-stock", json={"quantity_delta": 5}, headers=HEADERS)
        response = client.post(
            "/reservations",
            json={"sku_code": "SKU005", "quantity": 10, "idempotency_key": "idempotency-2"},
            headers=HEADERS,
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self):
        client.post("/skus", json={"sku_code": "SKU006", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU006/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        response1 = client.post(
            "/reservations",
            json={"sku_code": "SKU006", "quantity": 10, "idempotency_key": "idempotency-3"},
            headers=HEADERS,
        )
        response2 = client.post(
            "/reservations",
            json={"sku_code": "SKU006", "quantity": 10, "idempotency_key": "idempotency-3"},
            headers=HEADERS,
        )
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_confirm_reservation(self):
        client.post("/skus", json={"sku_code": "SKU007", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU007/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        res_response = client.post(
            "/reservations",
            json={"sku_code": "SKU007", "quantity": 10, "idempotency_key": "idempotency-4"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]
        response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["confirmed_at"] is not None

    def test_cancel_reservation(self):
        client.post("/skus", json={"sku_code": "SKU008", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU008/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        res_response = client.post(
            "/reservations",
            json={"sku_code": "SKU008", "quantity": 10, "idempotency_key": "idempotency-5"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]
        response = client.post(f"/reservations/{reservation_id}/cancel", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_cancel_confirmed_reservation_raises_error(self):
        client.post("/skus", json={"sku_code": "SKU009", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU009/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        res_response = client.post(
            "/reservations",
            json={"sku_code": "SKU009", "quantity": 10, "idempotency_key": "idempotency-6"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        response = client.post(f"/reservations/{reservation_id}/cancel", headers=HEADERS)
        assert response.status_code == 409


class TestOrderEndpoints:
    def test_list_orders(self):
        client.post("/skus", json={"sku_code": "SKU010", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU010/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        res_response = client.post(
            "/reservations",
            json={"sku_code": "SKU010", "quantity": 10, "idempotency_key": "idempotency-7"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        response = client.get("/orders", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["orders"]) >= 1

    def test_list_orders_pagination(self):
        client.post("/skus", json={"sku_code": "SKU011", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU011/adjust-stock", json={"quantity_delta": 200}, headers=HEADERS)
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku_code": "SKU011", "quantity": 10, "idempotency_key": f"idempotency-pagination-{i}"},
                headers=HEADERS,
            )
            reservation_id = res_response.json()["reservation_id"]
            client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        response = client.get("/orders?page=1&page_size=2", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5
        assert len(data["orders"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_get_order(self):
        client.post("/skus", json={"sku_code": "SKU012", "description": "Test"}, headers=HEADERS)
        client.post("/skus/SKU012/adjust-stock", json={"quantity_delta": 100}, headers=HEADERS)
        res_response = client.post(
            "/reservations",
            json={"sku_code": "SKU012", "quantity": 10, "idempotency_key": "idempotency-8"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]
        confirm_response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        # Get the order from the list
        orders_response = client.get("/orders", headers=HEADERS)
        order_id = orders_response.json()["orders"][0]["order_id"]
        response = client.get(f"/orders/{order_id}", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["sku_code"] == "SKU012"
        assert data["quantity"] == 10

    def test_list_orders_without_api_key(self):
        response = client.get("/orders")
        assert response.status_code == 403
