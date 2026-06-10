"""Tests for the service business logic layer."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    InsufficientStockError,
    ReservationAlreadyProcessedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        yield db_path


@pytest.fixture
def repository(temp_db):
    """Create a repository with temporary database."""
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    """Create a service with temporary repository."""
    return Service(repository)


class TestSKUOperations:
    """Tests for SKU creation and listing."""

    def test_create_sku(self, service):
        """Test creating a SKU."""
        result = service.create_sku("SKU001", "Widget", 100)
        assert result["id"] == "SKU001"
        assert result["name"] == "Widget"
        assert result["current_stock"] == 100

    def test_list_skus(self, service):
        """Test listing SKUs."""
        service.create_sku("SKU001", "Widget", 100)
        service.create_sku("SKU002", "Gadget", 50)

        skus = service.list_skus()
        assert len(skus) == 2
        assert skus[0]["id"] == "SKU001"
        assert skus[1]["id"] == "SKU002"

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        service.create_sku("SKU001", "Widget", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["current_stock"] == 150

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU001", "Widget", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["current_stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    """Tests for reservation logic."""

    def test_create_reservation_success(self, service):
        """Test successful reservation creation."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, 300)

        assert reservation.sku_id == "SKU001"
        assert reservation.quantity == 10
        assert reservation.status == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails with insufficient stock."""
        service.create_sku("SKU001", "Widget", 10)

        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 20, 300)

    def test_create_reservation_nonexistent_sku(self, service):
        """Test reservation fails for non-existent SKU."""
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", 10, 300)

    def test_create_reservation_deducts_stock(self, service):
        """Test that reservation deducts stock immediately."""
        service.create_sku("SKU001", "Widget", 100)
        service.create_reservation("SKU001", 40, 300)

        skus = service.list_skus()
        assert skus[0]["current_stock"] == 60

    def test_idempotent_reservation_retry(self, service):
        """Test idempotent reservation creation."""
        service.create_sku("SKU001", "Widget", 100)

        # First creation
        res1 = service.create_reservation(
            "SKU001", 10, 300, idempotency_key="key123"
        )

        # Retry with same key
        res2 = service.create_reservation(
            "SKU001", 10, 300, idempotency_key="key123"
        )

        assert res1.id == res2.id
        assert service.list_skus()[0]["current_stock"] == 90  # Stock deducted once

    def test_cancel_reservation_restores_stock(self, service):
        """Test that cancelling a reservation restores stock."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 30, 300)

        assert service.list_skus()[0]["current_stock"] == 70

        service.cancel_reservation(reservation.id)
        assert service.list_skus()[0]["current_stock"] == 100

    def test_cancel_nonexistent_reservation(self, service):
        """Test cancelling non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")

    def test_cancel_already_confirmed_reservation(self, service):
        """Test cancelling an already confirmed reservation."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, 300)

        service.confirm_reservation(reservation.id)

        with pytest.raises(ReservationAlreadyProcessedError):
            service.cancel_reservation(reservation.id)


class TestOrderConfirmation:
    """Tests for order confirmation logic."""

    def test_confirm_reservation_success(self, service):
        """Test successful reservation confirmation."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, 300)

        confirmed_res, order = service.confirm_reservation(reservation.id)

        assert confirmed_res.status == ReservationStatus.CONFIRMED
        assert order.reservation_id == reservation.id
        assert order.status.value == "confirmed"

    def test_confirm_nonexistent_reservation(self, service):
        """Test confirming non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_confirm_already_confirmed_reservation(self, service):
        """Test confirming an already confirmed reservation."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, 300)

        service.confirm_reservation(reservation.id)

        with pytest.raises(ReservationAlreadyProcessedError):
            service.confirm_reservation(reservation.id)

    def test_confirm_expired_reservation(self, service, monkeypatch):
        """Test confirming an expired reservation."""
        from datetime import timedelta

        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, 1)

        # Mock datetime to advance past expiration
        original_utcnow = datetime.utcnow

        def mock_utcnow():
            return original_utcnow() + timedelta(seconds=2)

        monkeypatch.setattr("commerce_service.service.datetime", type('obj', (object,), {
            'utcnow': mock_utcnow,
            'strptime': datetime.strptime,
        })())

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation.id)

    def test_confirm_reservation_does_not_restore_stock(self, service):
        """Test that confirming a reservation does not restore stock."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 30, 300)

        service.confirm_reservation(reservation.id)

        assert service.list_skus()[0]["current_stock"] == 70


class TestOrderListing:
    """Tests for order listing and pagination."""

    def test_list_orders_empty(self, service):
        """Test listing orders when none exist."""
        orders, total = service.list_orders(10, 0)
        assert len(orders) == 0
        assert total == 0

    def test_list_orders_with_limit(self, service):
        """Test pagination with limit."""
        service.create_sku("SKU001", "Widget", 1000)

        for i in range(5):
            res = service.create_reservation("SKU001", 10, 300)
            service.confirm_reservation(res.id)

        orders, total = service.list_orders(limit=2, offset=0)
        assert len(orders) == 2
        assert total == 5

    def test_list_orders_with_offset(self, service):
        """Test pagination with offset."""
        service.create_sku("SKU001", "Widget", 1000)

        order_ids = []
        for i in range(5):
            res = service.create_reservation("SKU001", 10, 300)
            _, order = service.confirm_reservation(res.id)
            order_ids.append(order.id)

        orders1, _ = service.list_orders(limit=2, offset=0)
        orders2, _ = service.list_orders(limit=2, offset=2)

        assert orders1[0].id != orders2[0].id

    def test_get_order(self, service):
        """Test retrieving a single order."""
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, 300)
        _, order = service.confirm_reservation(reservation.id)

        retrieved = service.get_order(order.id)
        assert retrieved is not None
        assert retrieved.id == order.id
        assert retrieved.reservation_id == reservation.id

    def test_get_nonexistent_order(self, service):
        """Test retrieving a non-existent order."""
        order = service.get_order("NONEXISTENT")
        assert order is None
