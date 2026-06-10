"""Tests for the service layer."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    SKUNotFoundError,
)
from commerce_service.repository import Repository, SKU, Stock, Reservation, Order, OrderItem


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    repo = Repository("sqlite:///:memory:")
    return repo


@pytest.fixture
def service(test_db):
    """Create a service with test database."""
    return CommerceService(test_db)


class TestSKUCreation:
    def test_create_sku(self, service):
        """Test creating a new SKU."""
        result = service.create_sku("PROD001", "Product 1")
        assert result.sku_code == "PROD001"
        assert result.name == "Product 1"
        assert result.id is not None


class TestStockAdjustment:
    def test_adjust_stock_increases(self, service):
        """Test increasing stock."""
        service.create_sku("PROD001", "Product 1")
        result = service.adjust_stock("PROD001", 100)
        assert result["available"] == 100
        assert result["reserved"] == 0

    def test_adjust_stock_decreases(self, service):
        """Test decreasing stock."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)
        result = service.adjust_stock("PROD001", -30)
        assert result["available"] == 70
        assert result["reserved"] == 0

    def test_adjust_stock_sku_not_found(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    def test_create_reservation_success(self, service):
        """Test successful reservation creation."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        result = service.create_reservation("PROD001", 10, "req-001")
        assert result.quantity == 10
        assert result.status == "pending"
        assert result.id is not None

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails with insufficient stock."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 5)

        with pytest.raises(InsufficientStockError):
            service.create_reservation("PROD001", 10, "req-001")

    def test_create_reservation_idempotency(self, service):
        """Test that same idempotency key returns same reservation."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        result1 = service.create_reservation("PROD001", 10, "req-001")
        result2 = service.create_reservation("PROD001", 10, "req-001")

        assert result1.id == result2.id
        assert result1.quantity == result2.quantity

    def test_create_reservation_sku_not_found(self, service):
        """Test reservation fails for non-existent SKU."""
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", 10, "req-001")

    def test_create_reservation_stock_reserved(self, service):
        """Test that reserved stock is tracked."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        service.create_reservation("PROD001", 50, "req-001")
        # Should not allow reserving more than available
        with pytest.raises(InsufficientStockError):
            service.create_reservation("PROD001", 60, "req-002")


class TestConfirmReservation:
    def test_confirm_reservation_success(self, service):
        """Test confirming a reservation."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        res = service.create_reservation("PROD001", 10, "req-001")
        order = service.confirm_reservation(res.id)

        assert order.status.value == "confirmed"
        assert len(order.items) == 1
        assert order.items[0].quantity == 10

    def test_confirm_reservation_not_found(self, service):
        """Test confirming non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_reservation_expired(self, service):
        """Test confirming an expired reservation."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        res = service.create_reservation("PROD001", 10, "req-001")

        # Manually expire the reservation
        session = service.repo.get_session()
        reservation = service.repo.get_reservation(session, res.id)
        reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
        session.close()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.id)


class TestCancelReservation:
    def test_cancel_reservation_success(self, service):
        """Test cancelling a reservation."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        res = service.create_reservation("PROD001", 10, "req-001")
        result = service.cancel_reservation(res.id)

        assert result["status"] == "cancelled"

        # Verify stock is released
        stock_result = service.adjust_stock("PROD001", 0)
        assert stock_result["available"] == 100  # Back to original

    def test_cancel_reservation_not_found(self, service):
        """Test cancelling non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)

    def test_cancel_reservation_already_confirmed(self, service):
        """Test cancelling an already confirmed reservation."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        res = service.create_reservation("PROD001", 10, "req-001")
        service.confirm_reservation(res.id)

        with pytest.raises(Exception):  # ServiceError about state
            service.cancel_reservation(res.id)


class TestOrderListing:
    def test_list_orders_empty(self, service):
        """Test listing orders when none exist."""
        result = service.list_orders()
        assert result["total"] == 0
        assert result["orders"] == []

    def test_list_orders_with_pagination(self, service):
        """Test pagination of orders."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        # Create multiple reservations and confirm them
        for i in range(15):
            res = service.create_reservation("PROD001", 1, f"req-{i}")
            service.confirm_reservation(res.id)

        # Test first page
        page1 = service.list_orders(offset=0, limit=10)
        assert len(page1["orders"]) == 10
        assert page1["total"] == 15
        assert page1["offset"] == 0
        assert page1["limit"] == 10

        # Test second page
        page2 = service.list_orders(offset=10, limit=10)
        assert len(page2["orders"]) == 5
        assert page2["total"] == 15
        assert page2["offset"] == 10

    def test_get_order(self, service):
        """Test retrieving a specific order."""
        service.create_sku("PROD001", "Product 1")
        service.adjust_stock("PROD001", 100)

        res = service.create_reservation("PROD001", 10, "req-001")
        order = service.confirm_reservation(res.id)

        retrieved = service.get_order(order.id)
        assert retrieved.id == order.id
        assert retrieved.status == order.status
