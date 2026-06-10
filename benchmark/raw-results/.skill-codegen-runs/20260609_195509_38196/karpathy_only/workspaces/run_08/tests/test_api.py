import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base
from commerce_service.security import API_KEY


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
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku_authorized(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["sku_id"] == "SKU001"
        assert response.json()["available_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_adjust_stock(self, client):
        # Create SKU first
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        # Adjust stock
        response = client.post(
            "/skus/SKU001/adjust-stock",
            json={"adjustment": 50},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 150

    def test_adjust_stock_not_found(self, client):
        response = client.post(
            "/skus/NONEXISTENT/adjust-stock",
            json={"adjustment": 10},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        # Create reservation
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        assert response.json()["quantity"] == 25

    def test_create_reservation_insufficient_stock(self, client):
        # Create SKU with limited stock
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 10},
            headers={"X-API-Key": API_KEY},
        )
        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 50,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        # Create reservation with idempotency key
        key = "idempotency-key-1"
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
                "idempotency_key": key,
            },
            headers={"X-API-Key": API_KEY},
        )
        # Retry with same key
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
                "idempotency_key": key,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_create_reservation_unauthorized(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
            },
        )
        assert response.status_code == 403


class TestConfirmEndpoint:
    def test_confirm_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]

        # Confirm
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["order_id"]


class TestCancelEndpoint:
    def test_cancel_reservation(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]

        # Cancel
        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrderEndpoints:
    def test_get_order(self, client):
        # Setup
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "customer_id": "CUST001",
                "quantity": 25,
            },
            headers={"X-API-Key": API_KEY},
        )
        order_res = client.post(
            f"/reservations/{res.json()['reservation_id']}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        order_id = order_res.json()["order_id"]

        # Get order
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["order_id"] == order_id

    def test_list_orders_pagination(self, client):
        # Setup SKU
        client.post(
            "/skus",
            json={"sku_id": "SKU001", "name": "Test Product", "initial_stock": 1000},
            headers={"X-API-Key": API_KEY},
        )

        # Create 5 orders
        for i in range(5):
            res = client.post(
                "/reservations",
                json={
                    "sku_id": "SKU001",
                    "customer_id": "CUST001",
                    "quantity": 10,
                },
                headers={"X-API-Key": API_KEY},
            )
            client.post(
                f"/reservations/{res.json()['reservation_id']}/confirm",
                json={},
                headers={"X-API-Key": API_KEY},
            )

        # Test pagination
        response = client.get("/customers/CUST001/orders?skip=0&limit=2")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        assert response.json()["total"] == 5

        response = client.get("/customers/CUST001/orders?skip=2&limit=3")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 3

    def test_list_orders_invalid_pagination(self, client):
        response = client.get("/customers/CUST001/orders?skip=-1&limit=10")
        assert response.status_code == 400

        response = client.get("/customers/CUST001/orders?skip=0&limit=200")
        assert response.status_code == 400
