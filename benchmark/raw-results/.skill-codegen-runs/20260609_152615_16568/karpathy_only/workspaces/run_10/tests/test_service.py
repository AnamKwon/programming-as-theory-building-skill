"""Tests for commerce service business logic."""

import pytest
from datetime import datetime, timedelta

from commerce_service.models import ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def repo():
    """Create an in-memory repository for testing."""
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    """Create a service instance."""
    return CommerceService(repo)


class TestSKUManagement:
    """Test SKU creation and stock adjustment."""

    def test_create_sku(self, service):
        """Test creating a SKU."""
        sku = service.create_sku("TEST-001", 100)
        assert sku.id == "TEST-001"
        assert sku.quantity == 100

    def test_adjust_stock(self, service):
        """Test adjusting stock."""
        service.create_sku("TEST-001", 100)
        sku = service.adjust_stock("TEST-001", 50)
        assert sku.quantity == 150

        sku = service.adjust_stock("TEST-001", -30)
        assert sku.quantity == 120

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    """Test reservation creation and state transitions."""

    def test_create_reservation(self, service):
        """Test creating a reservation."""
        service.create_sku("TEST-001", 100)
        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        assert reservation.sku_id == "TEST-001"
        assert reservation.quantity == 10
        assert reservation.state == ReservationState.PENDING

    def test_reservation_reduces_stock(self, service):
        """Test that reservations reduce available stock."""
        service.create_sku("TEST-001", 100)
        service.create_reservation("TEST-001", 30, "idempotency-key-1")

        sku = service.repo.get_sku("TEST-001")
        assert sku.quantity == 70

    def test_insufficient_stock_error(self, service):
        """Test that insufficient stock raises error."""
        service.create_sku("TEST-001", 50)

        with pytest.raises(InsufficientStockError):
            service.create_reservation("TEST-001", 100, "idempotency-key-1")

    def test_reservation_idempotency(self, service):
        """Test that same idempotency key returns same reservation."""
        service.create_sku("TEST-001", 100)

        reservation1 = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )
        reservation2 = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        assert reservation1.id == reservation2.id

    def test_reservation_nonexistent_sku(self, service):
        """Test creating reservation for non-existent SKU."""
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", 10, "idempotency-key-1")


class TestReservationConfirmation:
    """Test confirming reservations and creating orders."""

    def test_confirm_reservation(self, service):
        """Test confirming a reservation."""
        service.create_sku("TEST-001", 100)
        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        order = service.confirm_reservation(reservation.id)

        assert order.sku_id == "TEST-001"
        assert order.quantity == 10
        assert order.reservation_id == reservation.id

        confirmed_reservation = service.repo.get_reservation(reservation.id)
        assert confirmed_reservation.state == ReservationState.CONFIRMED

    def test_confirm_nonexistent_reservation(self, service):
        """Test confirming non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("nonexistent-id")

    def test_confirm_already_confirmed_reservation(self, service):
        """Test confirming an already confirmed reservation."""
        service.create_sku("TEST-001", 100)
        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        service.confirm_reservation(reservation.id)

        with pytest.raises(ReservationAlreadyConfirmedError):
            service.confirm_reservation(reservation.id)

    def test_confirm_expired_reservation(self, service):
        """Test confirming an expired reservation."""
        service.create_sku("TEST-001", 100)

        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        # Manually set expiration to past
        service.repo.conn.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (
                (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
                reservation.id,
            ),
        )
        service.repo.conn.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation.id)


class TestReservationCancellation:
    """Test cancelling reservations and releasing stock."""

    def test_cancel_reservation(self, service):
        """Test cancelling a reservation."""
        service.create_sku("TEST-001", 100)
        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        cancelled = service.cancel_reservation(reservation.id)

        assert cancelled.state == ReservationState.CANCELLED

        sku = service.repo.get_sku("TEST-001")
        assert sku.quantity == 100

    def test_cancel_nonexistent_reservation(self, service):
        """Test cancelling non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("nonexistent-id")

    def test_cancel_confirmed_reservation(self, service):
        """Test cancelling a confirmed reservation."""
        service.create_sku("TEST-001", 100)
        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        service.confirm_reservation(reservation.id)

        with pytest.raises(ReservationAlreadyConfirmedError):
            service.cancel_reservation(reservation.id)


class TestOrderLookup:
    """Test retrieving orders and pagination."""

    def test_get_order(self, service):
        """Test retrieving an order."""
        service.create_sku("TEST-001", 100)
        reservation = service.create_reservation(
            "TEST-001", 10, "idempotency-key-1"
        )

        order = service.confirm_reservation(reservation.id)

        retrieved = service.get_order(order.id)
        assert retrieved.id == order.id
        assert retrieved.sku_id == "TEST-001"

    def test_list_orders_pagination(self, service):
        """Test order pagination."""
        service.create_sku("TEST-001", 1000)

        # Create and confirm multiple reservations
        for i in range(5):
            reservation = service.create_reservation(
                "TEST-001", 10, f"idempotency-key-{i}"
            )
            service.confirm_reservation(reservation.id)

        total, orders = service.list_orders(limit=2, offset=0)
        assert total == 5
        assert len(orders) == 2

        total, orders = service.list_orders(limit=2, offset=2)
        assert len(orders) == 2

        total, orders = service.list_orders(limit=2, offset=4)
        assert len(orders) == 1
