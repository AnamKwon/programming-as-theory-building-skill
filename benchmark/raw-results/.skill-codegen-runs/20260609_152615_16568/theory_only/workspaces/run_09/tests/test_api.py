"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.app import app, get_db

TEST_API_KEY = "sk-test-commerce-service-key-123"


@pytest.fixture
def client():
    """Create a FastAPI test client with test database."""
    import tempfile
    import os

    # Use a temporary file-based database instead of :memory:
    # because SQLite :memory: dbs are separate per thread
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)

        def override_get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()
    finally:
        os.unlink(db_path)


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "SHOE-001"
        assert data["name"] == "Running Shoes"

    def test_create_sku_without_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
        )
        assert response.status_code == 401

    def test_create_sku_with_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_get_sku(self, client):
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        response = client.get("/skus/SHOE-001")
        assert response.status_code == 200
        assert response.json()["name"] == "Running Shoes"

    def test_get_nonexistent_sku(self, client):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404


class TestStockEndpoints:
    def test_get_stock(self, client):
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        response = client.get("/stock/SHOE-001")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] == 100
        assert data["reserved"] == 0

    def test_adjust_stock_increase(self, client):
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        response = client.post(
            "/stock/SHOE-001/adjust",
            json={"quantity_delta": 50},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["available"] == 150

    def test_adjust_stock_without_api_key(self, client):
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        response = client.post(
            "/stock/SHOE-001/adjust",
            json={"quantity_delta": 50},
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    @pytest.fixture(autouse=True)
    def setup_sku(self, client):
        """Create a test SKU before each test."""
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )

    def test_create_reservation_success(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["quantity"] == 5
        assert data["status"] == "reserved"

    def test_create_reservation_insufficient_stock(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 500},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 409

    def test_create_reservation_without_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
        )
        assert response.status_code == 401

    def test_create_reservation_with_idempotency_key(self, client):
        response1 = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5, "idempotency_key": "key-123"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        response2 = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5, "idempotency_key": "key-123"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_get_reservation(self, client):
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        response = client.get(f"/reservations/{res_id}")
        assert response.status_code == 200
        assert response.json()["quantity"] == 5

    def test_cancel_reservation(self, client):
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_reservation_without_api_key(self, client):
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        response = client.post(f"/reservations/{res_id}/cancel")
        assert response.status_code == 401

    def test_cancel_returns_stock(self, client):
        client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 10},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": TEST_API_KEY},
        )
        stock_response = client.get("/stock/SHOE-001")
        stock = stock_response.json()
        assert stock["available"] == 95
        assert stock["reserved"] == 5


class TestOrderConfirmationEndpoints:
    @pytest.fixture(autouse=True)
    def setup_sku(self, client):
        """Create a test SKU before each test."""
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )

    def test_confirm_reservation(self, client):
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["reservation_id"] == res_id

    def test_confirm_removes_reserved_stock(self, client):
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": TEST_API_KEY},
        )
        stock_response = client.get("/stock/SHOE-001")
        stock = stock_response.json()
        assert stock["available"] == 95
        assert stock["reserved"] == 0

    def test_confirm_without_api_key(self, client):
        create_res = client.post(
            "/reservations",
            json={"sku_id": "SHOE-001", "quantity": 5},
            headers={"X-API-Key": TEST_API_KEY},
        )
        res_id = create_res.json()["id"]
        response = client.post(f"/reservations/{res_id}/confirm")
        assert response.status_code == 401


class TestOrderEndpoints:
    @pytest.fixture(autouse=True)
    def setup_orders(self, client):
        """Create test orders before each test."""
        client.post(
            "/skus",
            json={"id": "SHOE-001", "name": "Running Shoes"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku_id": "SHOE-001", "quantity": 1},
                headers={"X-API-Key": TEST_API_KEY},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": TEST_API_KEY},
            )

    def test_get_order(self, client):
        orders_response = client.get("/orders?page=1&page_size=1")
        order_id = orders_response.json()["orders"][0]["id"]
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_list_orders_pagination_first_page(self, client):
        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["pages"] == 2

    def test_list_orders_pagination_second_page(self, client):
        response = client.get("/orders?page=2&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["page"] == 2

    def test_list_orders_default_pagination(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_list_orders_custom_page_size(self, client):
        response = client.get("/orders?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["pages"] == 3

    def test_list_orders_invalid_page(self, client):
        response = client.get("/orders?page=0")
        assert response.status_code == 422

    def test_list_orders_invalid_page_size(self, client):
        response = client.get("/orders?page_size=0")
        assert response.status_code == 422

    def test_list_orders_page_size_too_large(self, client):
        response = client.get("/orders?page_size=1000")
        assert response.status_code == 422
