import pytest
import tempfile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.app import app, get_db

API_KEY = "test-key"

@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    import os
    os.unlink(db_path)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestHealthAndBasicEndpoints:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_create_sku_requires_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
        )
        assert response.status_code == 403

    def test_create_sku_with_valid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["name"] == "Product"
        assert data["base_price"] == 10.0

    def test_get_sku_no_api_key_required(self, client):
        # Create SKU first
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )

        response = client.get("/skus/1")
        assert response.status_code == 200
        assert response.json()["sku"] == "SKU001"

    def test_get_nonexistent_sku(self, client):
        response = client.get("/skus/999")
        assert response.status_code == 404


class TestStockManagement:
    def test_adjust_stock_requires_api_key(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )

        response = client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
        )
        assert response.status_code == 403

    def test_adjust_stock_with_api_key(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )

        response = client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 100

    def test_get_stock(self, client):
        # Create and add stock
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )

        response = client.get("/skus/1/stock")
        assert response.status_code == 200
        assert response.json()["quantity"] == 100


class TestReservations:
    def test_create_reservation_requires_api_key(self, client):
        # Setup: create SKU and stock
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )

        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
        )
        assert response.status_code == 403

    def test_create_reservation_happy_path(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )

        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10, "ttl_seconds": 3600},
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == 1
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        # Setup: only 50 stock
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 50},
            headers={"x-api-key": API_KEY},
        )

        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 100},
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_with_idempotency_key(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )

        idempotency_key = "test-idempotency-001"

        # First request
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": idempotency_key,
            },
            headers={"x-api-key": API_KEY},
        )
        assert response1.status_code == 200
        res1_id = response1.json()["id"]

        # Retry with same key
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": idempotency_key,
            },
            headers={"x-api-key": API_KEY},
        )
        assert response2.status_code == 200
        res2_id = response2.json()["id"]
        assert res1_id == res2_id

    def test_get_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
            headers={"x-api-key": API_KEY},
        )
        res_id = create_res.json()["id"]

        response = client.get(f"/reservations/{res_id}")
        assert response.status_code == 200
        assert response.json()["id"] == res_id

    def test_confirm_reservation_requires_api_key(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
            headers={"x-api-key": API_KEY},
        )
        res_id = create_res.json()["id"]

        response = client.post(f"/reservations/{res_id}/confirm")
        assert response.status_code == 403

    def test_confirm_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
            headers={"x-api-key": API_KEY},
        )
        res_id = create_res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_cancel_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
            headers={"x-api-key": API_KEY},
        )
        res_id = create_res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrders:
    def test_list_orders_requires_api_key(self, client):
        response = client.get("/orders")
        assert response.status_code == 403

    def test_list_orders_pagination(self, client):
        # Setup: create 15 orders
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 500},
            headers={"x-api-key": API_KEY},
        )

        for i in range(15):
            client.post(
                "/reservations",
                json={"sku_id": 1, "quantity": 10},
                headers={"x-api-key": API_KEY},
            )

        # List page 1
        response = client.get(
            "/orders?page=1&page_size=10",
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1

        # List page 2
        response = client.get(
            "/orders?page=2&page_size=10",
            headers={"x-api-key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5

    def test_get_order(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku": "SKU001", "name": "Product", "base_price": 10.0},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/skus/1/stock",
            json={"quantity_delta": 100},
            headers={"x-api-key": API_KEY},
        )
        client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
            headers={"x-api-key": API_KEY},
        )

        response = client.get("/orders/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["status"] == "pending"
        assert data["quantity_reserved"] == 10

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders/999")
        assert response.status_code == 400
