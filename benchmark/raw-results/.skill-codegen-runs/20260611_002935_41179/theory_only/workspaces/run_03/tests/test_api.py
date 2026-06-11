"""API endpoint tests."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db, Base
from commerce_service.models import ReservationModel, SKUModel

# Test database setup
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(bind=engine)


def override_get_db():
    """Override get_db for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# Valid API token for tests
VALID_TOKEN = "test-token-secret"
INVALID_TOKEN = "invalid-token"


class TestHealth:
    """Tests for health endpoint."""

    def test_health_check_success(self):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    """Tests for SKU endpoints."""

    def test_create_sku_success(self):
        """Test successful SKU creation."""
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["total_stock"] == 100
        assert data["available_stock"] == 100

    def test_create_sku_unauthorized(self):
        """Test SKU creation without token."""
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_token(self):
        """Test SKU creation with invalid token."""
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
        )
        assert response.status_code == 401


class TestStockAdjustmentEndpoints:
    """Tests for stock adjustment endpoints."""

    def test_adjust_stock_increase(self):
        """Test stock adjustment increase."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": 50},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_stock"] == 150

    def test_adjust_stock_decrease(self):
        """Test stock adjustment decrease."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": -30},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_stock"] == 70

    def test_adjust_stock_unauthorized(self):
        """Test stock adjustment without token."""
        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "amount": 50},
        )
        assert response.status_code == 403


class TestReservationEndpoints:
    """Tests for reservation endpoints."""

    def test_create_reservation_success(self):
        """Test successful reservation creation."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["quantity"] == 50
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self):
        """Test reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 30},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_idempotent_reservation(self):
        """Test idempotent reservation creation."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        request_data = {
            "sku": "TEST-001",
            "quantity": 50,
            "idempotency_key": "KEY-001",
        }
        response1 = client.post(
            "/reservations",
            json=request_data,
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        response2 = client.post(
            "/reservations",
            json=request_data,
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        data1 = response1.json()
        data2 = response2.json()
        assert data1["id"] == data2["id"]
        assert response1.status_code == 201
        assert response2.status_code == 201

    def test_create_reservation_unauthorized(self):
        """Test reservation creation without token."""
        response = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
        )
        assert response.status_code == 403


class TestReservationConfirmationEndpoints:
    """Tests for reservation confirmation endpoints."""

    def test_confirm_reservation_success(self):
        """Test successful reservation confirmation."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"

    def test_confirm_reservation_expired(self):
        """Test confirming expired reservation."""
        db = next(override_get_db())

        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res.json()["id"]

        # Manually set created_at to 301 seconds ago
        reservation = db.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()
        reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
        db.commit()

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

        db.close()

    def test_confirm_reservation_unauthorized(self):
        """Test reservation confirmation without token."""
        response = client.post(
            "/reservations/1/confirm",
        )
        assert response.status_code == 403


class TestReservationCancellationEndpoints:
    """Tests for reservation cancellation endpoints."""

    def test_cancel_reservation_success(self):
        """Test successful reservation cancellation."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_restores_stock(self):
        """Test that cancellation restores stock."""
        db = next(override_get_db())

        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "KEY-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res.json()["id"]

        sku_before = db.query(SKUModel).filter(SKUModel.sku == "TEST-001").first()
        assert sku_before.available_stock == 50

        client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        sku_after = db.query(SKUModel).filter(SKUModel.sku == "TEST-001").first()
        assert sku_after.available_stock == 100

        db.close()

    def test_cancel_reservation_unauthorized(self):
        """Test reservation cancellation without token."""
        response = client.post(
            "/reservations/1/cancel",
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    """Tests for order endpoints."""

    def test_get_orders_empty(self):
        """Test getting orders when empty."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0

    def test_get_orders_pagination(self):
        """Test order pagination."""
        client.post(
            "/skus",
            json={"sku": "TEST-001", "initial_stock": 500},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        # Create multiple orders
        for i in range(25):
            res = client.post(
                "/reservations",
                json={
                    "sku": "TEST-001",
                    "quantity": 5,
                    "idempotency_key": f"KEY-{i:03d}",
                },
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

        # Test first page
        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 25

        # Test second page
        response = client.get("/orders?page=2&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["page"] == 2

        # Test third page
        response = client.get("/orders?page=3&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5

    def test_get_orders_invalid_page(self):
        """Test order pagination with invalid page."""
        response = client.get("/orders?page=0&size=10")
        assert response.status_code == 400

    def test_get_orders_invalid_size(self):
        """Test order pagination with invalid size."""
        response = client.get("/orders?page=1&size=0")
        assert response.status_code == 400


class TestWorkflow:
    """Integration tests for complete workflow."""

    def test_complete_workflow(self):
        """Test complete SKU -> Reserve -> Confirm -> Order workflow."""
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "WORKFLOW-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert sku_response.status_code == 201

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={
                "sku": "WORKFLOW-001",
                "quantity": 50,
                "idempotency_key": "WORKFLOW-KEY-001",
            },
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert res_response.status_code == 201
        reservation_id = res_response.json()["id"]

        # Confirm reservation
        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert confirm_response.status_code == 200

        # Get orders
        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        data = orders_response.json()
        assert len(data["orders"]) == 1
        assert data["orders"][0]["reservation_id"] == reservation_id
