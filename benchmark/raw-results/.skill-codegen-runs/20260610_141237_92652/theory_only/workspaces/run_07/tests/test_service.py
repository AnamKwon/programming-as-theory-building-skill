"""Service layer unit tests."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from commerce_service.service import CommerceService
from commerce_service.repository import Repository
from commerce_service.models import Reservation, ReservationStatus, SKU, Order


@pytest.fixture
def repository():
    """Create an in-memory test repository."""
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repository):
    """Create a service with test repository."""
    return CommerceService(repository)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert "id" in result


def test_create_sku_duplicate(service):
    """Test duplicate SKU creation fails."""
    service.create_sku("SKU001", 100)
    result = service.create_sku("SKU001", 50)
    assert "error" in result


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -10)
    assert result["available_stock"] == 90

    result = service.adjust_stock("SKU001", 20)
    assert result["available_stock"] == 110


def test_adjust_stock_nonexistent_sku(service):
    """Test adjustment on nonexistent SKU."""
    result = service.adjust_stock("NONEXISTENT", 10)
    assert result is None


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("SKU001", 100)
    reservation, error = service.create_reservation("SKU001", 50, "key123")

    assert error is None
    assert reservation.sku == "SKU001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"
    assert reservation.id is not None


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails with insufficient stock."""
    service.create_sku("SKU001", 30)
    reservation, error = service.create_reservation("SKU001", 50, "key123")

    assert error == "Insufficient stock"
    assert reservation is None


def test_create_reservation_nonexistent_sku(service):
    """Test reservation fails for nonexistent SKU."""
    reservation, error = service.create_reservation("NONEXISTENT", 10, "key123")

    assert error == "SKU not found"
    assert reservation is None


def test_reservation_idempotency(service):
    """Test idempotent reservation creation."""
    service.create_sku("SKU001", 100)

    # First request
    res1, err1 = service.create_reservation("SKU001", 30, "idempotency-key-1")
    assert err1 is None
    assert res1.id == 1

    # Second request with same key
    res2, err2 = service.create_reservation("SKU001", 30, "idempotency-key-1")
    assert err2 is None
    assert res2.id == 1
    assert res1.created_at == res2.created_at

    # Verify stock was only deducted once
    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 70


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key123")

    result, error = service.confirm_reservation(reservation.id)

    assert error is None
    assert result["status"] == "CONFIRMED"
    assert "order_id" in result


def test_confirm_nonexistent_reservation(service):
    """Test confirmation of nonexistent reservation."""
    result, error = service.confirm_reservation(999)

    assert error == "Reservation not found"
    assert result is None


def test_confirm_non_pending_reservation(service):
    """Test confirmation of non-pending reservation fails."""
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key123")

    # Confirm once
    service.confirm_reservation(reservation.id)

    # Try to confirm again
    result, error = service.confirm_reservation(reservation.id)
    assert error is not None
    assert result is None


def test_confirm_expired_reservation(service):
    """Test that expired reservation cannot be confirmed."""
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key123")

    # Mock the reservation's created_at to be old
    with patch("commerce_service.service.datetime") as mock_datetime:
        old_time = datetime.utcnow() - timedelta(seconds=400)
        mock_datetime.utcnow.return_value = old_time
        # Need to update the actual reservation in database
        service.repo.get_session().query(Reservation).filter(
            Reservation.id == reservation.id
        ).update({"created_at": old_time})
        service.repo.get_session().commit()

    result, error = service.confirm_reservation(reservation.id)

    assert error == "Reservation expired"
    assert result is None

    # Verify stock was restored
    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 100


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key123")

    result, error = service.cancel_reservation(reservation.id)

    assert error is None
    assert result["status"] == "CANCELLED"

    # Verify stock was restored
    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 100


def test_cancel_non_pending_reservation(service):
    """Test cancellation of non-pending reservation fails."""
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key123")

    # Confirm first
    service.confirm_reservation(reservation.id)

    # Try to cancel confirmed reservation
    result, error = service.cancel_reservation(reservation.id)
    assert error is not None
    assert result is None


def test_get_orders_empty(service):
    """Test getting orders when none exist."""
    result = service.get_orders(page=1, size=10)

    assert result.page == 1
    assert result.size == 10
    assert result.total == 0
    assert len(result.orders) == 0


def test_get_orders_pagination(service):
    """Test orders pagination."""
    service.create_sku("SKU001", 100)

    # Create multiple reservations and orders
    for i in range(25):
        res, _ = service.create_reservation("SKU001", 1, f"key-{i}")
        service.confirm_reservation(res.id)

    # Test first page
    result = service.get_orders(page=1, size=10)
    assert result.total == 25
    assert len(result.orders) == 10

    # Test second page
    result = service.get_orders(page=2, size=10)
    assert len(result.orders) == 10

    # Test third page
    result = service.get_orders(page=3, size=10)
    assert len(result.orders) == 5


def test_happy_path_workflow(service):
    """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
    # Create SKU
    sku_result = service.create_sku("WIDGET-001", 50)
    assert sku_result["available_stock"] == 50

    # Create reservation
    reservation, error = service.create_reservation("WIDGET-001", 20, "order-key-1")
    assert error is None
    assert reservation.status == "PENDING"

    # Verify stock was deducted
    sku = service.repo.get_sku_by_name("WIDGET-001")
    assert sku.available_stock == 30

    # Confirm reservation
    confirm_result, error = service.confirm_reservation(reservation.id)
    assert error is None
    assert confirm_result["status"] == "CONFIRMED"

    # Get orders
    orders = service.get_orders(page=1, size=10)
    assert orders.total == 1
    assert orders.orders[0].reservation_id == reservation.id
