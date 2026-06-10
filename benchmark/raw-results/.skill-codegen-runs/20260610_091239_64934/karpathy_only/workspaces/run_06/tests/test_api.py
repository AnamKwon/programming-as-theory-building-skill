"""Tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """Create a test client with test database dependency."""

    def override_get_db():
        return db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


API_KEY = "test-key"


class TestHealth:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSkuEndpoints:
    """Tests for SKU endpoints."""

    def test_create_sku(self, client):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku_code": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "PROD001"
        assert data["stock_quantity"] == 100

    def test_create_sku_missing_api_key(self, client):
        """Test creating a SKU without API key."""
        response = client.post(
            "/skus",
            json={"sku_code": "PROD002", "initial_stock": 100},
        )
        assert response.status_code == 401
        assert "Missing X-API-Key" in response.json()["detail"]

    def test_create_sku_invalid_api_key(self, client):
        """Test creating a SKU with invalid API key."""
        response = client.post(
            "/skus",
            json={"sku_code": "PROD003", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    def test_adjust_stock(self, client):
        """Test adjusting stock."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD004", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        response = client.patch(
            f"/skus/{sku_id}/stock",
            json={"quantity_delta": 25},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["stock_quantity"] == 125

    def test_adjust_stock_negative(self, client):
        """Test decreasing stock."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD005", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        response = client.patch(
            f"/skus/{sku_id}/stock",
            json={"quantity_delta": -30},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["stock_quantity"] == 70

    def test_adjust_stock_non_existent_sku(self, client):
        """Test adjusting stock for non-existent SKU."""
        response = client.patch(
            "/skus/999/stock",
            json={"quantity_delta": 10},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    """Tests for reservation endpoints."""

    def test_create_reservation_success(self, client):
        """Test creating a reservation with sufficient stock."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD006", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "test-idempotency-1",
                "ttl_seconds": 3600,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        """Test creating a reservation with insufficient stock."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD007", "initial_stock": 10},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 20,
                "idempotency_key": "test-idempotency-2",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self, client):
        """Test idempotent reservation creation."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD008", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        key = "test-idempotency-3"
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 25,
                "idempotency_key": key,
            },
            headers={"X-API-Key": API_KEY},
        )
        id1 = response1.json()["id"]

        response2 = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 25,
                "idempotency_key": key,
            },
            headers={"X-API-Key": API_KEY},
        )
        id2 = response2.json()["id"]

        assert id1 == id2
        assert response1.status_code == 201
        assert response2.status_code == 201

    def test_create_reservation_missing_api_key(self, client):
        """Test creating a reservation without API key."""
        response = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": "test-idempotency-4",
            },
        )
        assert response.status_code == 401

    def test_confirm_reservation_success(self, client):
        """Test confirming a pending reservation."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD009", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "test-idempotency-5",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CONFIRMED"

    def test_confirm_reservation_expired(self, client, db_session):
        """Test confirming an expired reservation."""
        from datetime import datetime, timedelta

        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD010", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "test-idempotency-6",
                "ttl_seconds": 1,
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res_response.json()["id"]

        from commerce_service.models import ReservationORM

        res = db_session.query(ReservationORM).filter_by(id=reservation_id).first()
        res.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db_session.commit()

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 410

    def test_cancel_reservation_success(self, client):
        """Test cancelling a reservation."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD011", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "test-idempotency-7",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_reservation_missing_api_key(self, client):
        """Test cancelling a reservation without API key."""
        response = client.post(
            "/reservations/1/cancel",
            json={},
        )
        assert response.status_code == 401


class TestOrderEndpoints:
    """Tests for order endpoints."""

    def test_get_order(self, client):
        """Test retrieving an order."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD012", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 30,
                "idempotency_key": "test-idempotency-8",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res_response.json()["id"]

        conf_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )

        order_id = reservation_id

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == reservation_id
        assert data["status"] == "CONFIRMED"

    def test_get_order_not_found(self, client):
        """Test retrieving non-existent order."""
        response = client.get("/orders/999")
        assert response.status_code == 404

    def test_list_orders_pagination(self, client):
        """Test listing orders with pagination."""
        sku_response = client.post(
            "/skus",
            json={"sku_code": "PROD013", "initial_stock": 1000},
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_response.json()["id"]

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku_id": sku_id,
                    "quantity": 10,
                    "idempotency_key": f"test-idempotency-{i}",
                },
                headers={"X-API-Key": API_KEY},
            )
            reservation_id = res_response.json()["id"]

            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={},
                headers={"X-API-Key": API_KEY},
            )

        response = client.get("/orders?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["has_more"] is True
        assert data["cursor"] is not None

        response2 = client.get("/orders?limit=10&offset=10")
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 5
        assert data2["has_more"] is False

    def test_list_orders_invalid_limit(self, client):
        """Test listing orders with invalid limit."""
        response = client.get("/orders?limit=101")
        assert response.status_code == 422

    def test_list_orders_invalid_offset(self, client):
        """Test listing orders with invalid offset."""
        response = client.get("/orders?offset=-1")
        assert response.status_code == 422
