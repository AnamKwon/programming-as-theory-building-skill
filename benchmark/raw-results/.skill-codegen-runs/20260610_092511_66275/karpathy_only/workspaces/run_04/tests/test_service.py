"""Tests for the commerce service business logic."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStatusTransitionError,
    ReservationExpiredError,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        yield db_path


@pytest.fixture
def repository(temp_db):
    """Create a repository with a temporary database."""
    return Repository(db_path=temp_db)


@pytest.fixture
def service(repository):
    """Create a service with a temporary repository."""
    return CommerceService(repository)


class TestSKUOperations:
    """Tests for SKU operations."""

    def test_create_sku(self, service):
        """Test creating a new SKU."""
        result = service.create_sku("SKU-001", 100)
        assert result["sku_id"] == "SKU-001"
        assert result["stock"] == 100
        assert result["created_at"] is not None

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        service.create_sku("SKU-001", 50)
        result = service.adjust_stock("SKU-001", 25)
        assert result["stock"] == 75

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", -30)
        assert result["stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock("SKU-NONE", 10)


class TestReservations:
    """Tests for reservation operations."""

    def test_create_reservation_success(self, service):
        """Test creating a reservation with sufficient stock."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        assert reservation["status"] == "pending"
        assert reservation["quantity"] == 30
        assert reservation["sku_id"] == "SKU-001"

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails when stock is insufficient."""
        service.create_sku("SKU-001", 20)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU-001", 50, "idempotency-key-1")

    def test_reservation_idempotency(self, service):
        """Test that same idempotency key returns the same reservation."""
        service.create_sku("SKU-001", 100)
        res1 = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        res2 = service.create_reservation(
            "SKU-001", 50, "idempotency-key-1"
        )
        assert res1["reservation_id"] == res2["reservation_id"]
        assert res1["quantity"] == 30  # Should still be 30, not 50

    def test_reservation_stock_adjustment(self, service):
        """Test that creating a reservation reduces stock."""
        service.create_sku("SKU-001", 100)
        service.create_reservation("SKU-001", 30, "idempotency-key-1")
        sku = service.repo.get_sku("SKU-001")
        assert sku["stock"] == 70  # 100 - 30

    def test_cancel_reservation_returns_stock(self, service):
        """Test that cancelling a reservation returns stock."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        service.cancel_reservation(reservation["reservation_id"])
        sku = service.repo.get_sku("SKU-001")
        assert sku["stock"] == 100  # Stock should be returned

    def test_cancel_already_cancelled_reservation(self, service):
        """Test that cancelling an already-cancelled reservation fails."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        service.cancel_reservation(reservation["reservation_id"])
        with pytest.raises(InvalidStatusTransitionError):
            service.cancel_reservation(reservation["reservation_id"])

    def test_confirm_reservation_success(self, service):
        """Test confirming a pending reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        result = service.confirm_reservation(reservation["reservation_id"])
        assert result["reservation"]["status"] == "confirmed"
        assert result["order"]["status"] == "completed"
        assert result["order"]["quantity"] == 30

    def test_confirm_already_confirmed_reservation(self, service):
        """Test that confirming an already-confirmed reservation fails."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        service.confirm_reservation(reservation["reservation_id"])
        with pytest.raises(InvalidStatusTransitionError):
            service.confirm_reservation(reservation["reservation_id"])

    def test_confirm_expired_reservation(self, service):
        """Test that confirming an expired reservation fails."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        # Manually expire the reservation
        repo = service.repo
        conn = repo._get_conn()
        cursor = conn.cursor()
        expired_time = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        cursor.execute(
            "UPDATE reservations SET expires_at = ? WHERE reservation_id = ?",
            (expired_time, reservation["reservation_id"]),
        )
        conn.commit()
        conn.close()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation["reservation_id"])


class TestOrders:
    """Tests for order operations."""

    def test_list_orders_empty(self, service):
        """Test listing orders when none exist."""
        orders, total = service.list_orders()
        assert orders == []
        assert total == 0

    def test_list_orders_with_pagination(self, service):
        """Test listing orders with pagination."""
        service.create_sku("SKU-001", 100)
        for i in range(15):
            reservation = service.create_reservation(
                "SKU-001", 1, f"idempotency-key-{i}"
            )
            service.confirm_reservation(reservation["reservation_id"])

        orders, total = service.list_orders(limit=10, offset=0)
        assert len(orders) == 10
        assert total == 15

        orders2, _ = service.list_orders(limit=10, offset=10)
        assert len(orders2) == 5

    def test_get_order(self, service):
        """Test retrieving a single order."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation(
            "SKU-001", 30, "idempotency-key-1"
        )
        result = service.confirm_reservation(reservation["reservation_id"])
        order_id = result["order"]["order_id"]

        order = service.get_order(order_id)
        assert order["order_id"] == order_id
        assert order["quantity"] == 30
        assert order["status"] == "completed"

    def test_get_nonexistent_order(self, service):
        """Test retrieving a non-existent order."""
        with pytest.raises(ValueError, match="not found"):
            service.get_order("ORDER-NONE")
