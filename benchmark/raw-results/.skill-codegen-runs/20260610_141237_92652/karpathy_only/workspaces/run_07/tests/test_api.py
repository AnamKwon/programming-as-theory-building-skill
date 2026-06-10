"""Integration tests for API endpoints."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import init_db, SessionLocal

API_KEY = "test-key-123"


@pytest.fixture(scope="function")
def test_db():
    """Create a test database."""
    db_fd, db_path = tempfile.mkstemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from src.commerce_service.repository import engine, Base
    Base.metadata.drop_all(bind=engine)
    init_db()

    yield SessionLocal()

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(test_db):
    """Create a test client."""
    return TestClient(app)


class TestHealth:
    """Test health endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKU:
    """Test SKU endpoints."""

    def test_create_sku_success(self, client):
        """Test successful SKU creation."""
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["stock"] == 100

    def test_create_sku_missing_auth(self, client):
        """Test SKU creation without authentication."""
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_auth(self, client):
        """Test SKU creation with invalid API key."""
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_increase(self, client):
        """Test stock increase."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": 50},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stock"] == 150

    def test_adjust_stock_decrease(self, client):
        """Test stock decrease."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": -30},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stock"] == 70


class TestReservation:
    """Test reservation endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        """Setup test SKU."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )

    def test_create_reservation_success(self, client):
        """Test successful reservation creation."""
        response = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["quantity"] == 10
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        """Test reservation with insufficient stock."""
        response = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 150,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client):
        """Test idempotent reservation creation."""
        response1 = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response1.status_code == 201
        data1 = response1.json()

        response2 = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response2.status_code == 201
        data2 = response2.json()

        assert data1["id"] == data2["id"]

    def test_confirm_reservation_success(self, client):
        """Test successful reservation confirmation."""
        res = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"

    def test_cancel_reservation_success(self, client):
        """Test successful reservation cancellation."""
        res = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_reservation_restores_stock(self, client):
        """Test that cancellation restores stock."""
        client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )

        sku_response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": 0},
            headers={"X-API-Key": API_KEY},
        )
        stock_after_first = sku_response.json()["stock"]

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 5,
                "idempotency_key": "key-2",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": API_KEY},
        )

        sku_response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": 0},
            headers={"X-API-Key": API_KEY},
        )
        stock_after_cancel = sku_response.json()["stock"]

        assert stock_after_cancel == stock_after_first


class TestOrders:
    """Test order endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        """Setup test SKU and orders."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )

        for i in range(3):
            res = client.post(
                "/reservations",
                json={
                    "sku": "TEST-001",
                    "quantity": 10,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": API_KEY},
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": API_KEY},
            )

    def test_get_orders_success(self, client):
        """Test successful orders retrieval."""
        response = client.get(
            "/orders",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 3
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 3

    def test_get_orders_pagination(self, client):
        """Test pagination."""
        response = client.get(
            "/orders?page=1&size=2",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 2
        assert data["page"] == 1
        assert data["size"] == 2
        assert data["total"] == 3

    def test_get_orders_missing_auth(self, client):
        """Test orders retrieval without authentication."""
        response = client.get("/orders")
        assert response.status_code == 401


class TestExpiration:
    """Test reservation expiration."""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        """Setup test SKU."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )

    def test_confirm_expired_reservation(self, client):
        """Test confirmation of expired reservation."""
        from unittest.mock import patch
        from datetime import datetime, timedelta

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST-001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]

        with patch("src.commerce_service.service.datetime") as mock_datetime:
            now = datetime.utcnow()
            old_time = now - timedelta(seconds=400)

            from src.commerce_service.repository import SessionLocal, ReservationModel
            db = SessionLocal()
            reservation = db.query(ReservationModel).filter_by(id=reservation_id).first()
            reservation.created_at = old_time
            db.commit()
            db.close()

            mock_datetime.utcnow.return_value = now

            response = client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": API_KEY},
            )
            assert response.status_code == 400
            assert "Reservation expired" in response.json()["detail"]
