"""Tests for the commerce service business logic."""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from src.commerce_service.models import ReservationStatus, OrderStatus
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    os.unlink(path)


@pytest.fixture
def service(temp_db):
    """Create a service with temporary database."""
    return CommerceService(temp_db)


class TestSKUCreation:
    def test_create_sku_success(self, service):
        """Test successful SKU creation."""
        response = service.create_sku("SKU001", "Widget", 99.99, 100)

        assert response.sku_id == "SKU001"
        assert response.name == "Widget"
        assert response.price == 99.99
        assert isinstance(response.created_at, datetime)

    def test_create_sku_duplicate_fails(self, service):
        """Test that duplicate SKU creation fails."""
        service.create_sku("SKU001", "Widget", 99.99, 100)

        with pytest.raises(ValueError, match="already exists"):
            service.create_sku("SKU001", "Different", 50.0, 50)


class TestStockAdjustment:
    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        service.create_sku("SKU001", "Widget", 99.99, 50)
        result = service.adjust_stock("SKU001", 25)

        assert result["available_quantity"] == 75

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        result = service.adjust_stock("SKU001", -30)

        assert result["available_quantity"] == 70

    def test_adjust_stock_insufficient_fails(self, service):
        """Test that decreasing below zero fails."""
        service.create_sku("SKU001", "Widget", 99.99, 50)

        with pytest.raises(ValueError, match="Insufficient available inventory"):
            service.adjust_stock("SKU001", -100)

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjustment on non-existent SKU fails."""
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_success(self, service):
        """Test successful reservation creation."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        response = service.create_reservation("SKU001", 10, "idempotency-key-1")

        assert response.sku_id == "SKU001"
        assert response.quantity == 10
        assert response.status == ReservationStatus.PENDING
        assert response.expires_at > response.created_at

    def test_create_reservation_idempotent(self, service):
        """Test that same idempotency key returns same reservation."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        resp1 = service.create_reservation("SKU001", 10, "idempotency-key-1")
        resp2 = service.create_reservation("SKU001", 20, "idempotency-key-1")

        assert resp1.reservation_id == resp2.reservation_id
        assert resp2.quantity == 10  # Original quantity, not the retry

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails with insufficient stock."""
        service.create_sku("SKU001", "Widget", 99.99, 50)

        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU001", 100, "idempotency-key-1")

    def test_create_reservation_nonexistent_sku(self, service):
        """Test reservation on non-existent SKU fails."""
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation("NONEXISTENT", 10, "idempotency-key-1")

    def test_confirm_reservation_success(self, service):
        """Test successful reservation confirmation."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
        response = service.confirm_reservation(reservation.reservation_id)

        assert response.status == ReservationStatus.CONFIRMED

    def test_confirm_reservation_not_pending(self, service):
        """Test confirming non-pending reservation fails."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
        service.confirm_reservation(reservation.reservation_id)

        with pytest.raises(ValueError, match="Cannot confirm"):
            service.confirm_reservation(reservation.reservation_id)

    def test_cancel_reservation_success(self, service):
        """Test successful reservation cancellation."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
        response = service.cancel_reservation(reservation.reservation_id)

        assert response.status == ReservationStatus.CANCELLED

    def test_cancel_reservation_releases_inventory(self, service):
        """Test that cancelling reservation releases inventory."""
        service.create_sku("SKU001", "Widget", 99.99, 100)
        service.create_reservation("SKU001", 30, "idempotency-key-1")

        # Inventory should be reserved
        inv = service.db.get_inventory("SKU001")
        assert inv["available_quantity"] == 70
        assert inv["reserved_quantity"] == 30

        # Cancel should release
        reservation = service.db.get_reservation_by_idempotency_key("idempotency-key-1")
        service.cancel_reservation(reservation["reservation_id"])

        inv = service.db.get_inventory("SKU001")
        assert inv["available_quantity"] == 100
        assert inv["reserved_quantity"] == 0


class TestOrderCreation:
    def test_get_orders_empty(self, service):
        """Test listing orders on empty database."""
        orders, total = service.get_orders()

        assert orders == []
        assert total == 0

    def test_get_orders_pagination(self, service):
        """Test order pagination."""
        service.create_sku("SKU001", "Widget", 99.99, 1000)

        for i in range(25):
            reservation = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(reservation.reservation_id)

        orders, total = service.get_orders(skip=0, limit=10)
        assert len(orders) == 10
        assert total == 25

        orders2, _ = service.get_orders(skip=10, limit=10)
        assert len(orders2) == 10

        # Orders should be in reverse chronological order
        assert orders[0].created_at > orders[1].created_at

    def test_get_orders_limit(self, service):
        """Test that limit is respected."""
        service.create_sku("SKU001", "Widget", 99.99, 100)

        for i in range(5):
            reservation = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(reservation.reservation_id)

        orders, _ = service.get_orders(limit=3)
        assert len(orders) == 3


class TestIntegration:
    def test_full_reservation_flow(self, service):
        """Test complete reservation to order flow."""
        # Create SKU
        sku = service.create_sku("SKU001", "Premium Widget", 199.99, 100)
        assert sku.sku_id == "SKU001"

        # Check initial inventory
        inv = service.db.get_inventory("SKU001")
        assert inv["available_quantity"] == 100

        # Create reservation
        res = service.create_reservation("SKU001", 25, "order-123")
        assert res.quantity == 25
        assert res.status == ReservationStatus.PENDING

        # Check inventory after reservation
        inv = service.db.get_inventory("SKU001")
        assert inv["available_quantity"] == 75
        assert inv["reserved_quantity"] == 25

        # Confirm reservation
        confirmed = service.confirm_reservation(res.reservation_id)
        assert confirmed.status == ReservationStatus.CONFIRMED

        # Check inventory after confirmation
        inv = service.db.get_inventory("SKU001")
        assert inv["available_quantity"] == 75
        assert inv["reserved_quantity"] == 0

        # Check order was created
        orders, total = service.get_orders()
        assert total == 1
        assert orders[0].quantity == 25
        assert orders[0].status == OrderStatus.CONFIRMED
