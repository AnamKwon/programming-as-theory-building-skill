"""Tests for the service layer business logic."""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidReservationStateError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repository(temp_db):
    """Create a repository instance with temp database."""
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    """Create a service instance."""
    return CommerceService(repository)


def test_create_sku(service):
    """Test creating a new SKU."""
    sku = service.create_sku("Widget", 100)
    assert sku.id is not None
    assert sku.product_name == "Widget"
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_adjust_stock(service):
    """Test adjusting stock levels."""
    sku = service.create_sku("Widget", 100)
    adjusted = service.adjust_stock(sku.id, 50)
    assert adjusted.available_stock == 150

    adjusted = service.adjust_stock(sku.id, -30)
    assert adjusted.available_stock == 120


def test_adjust_stock_negative_fails(service):
    """Test that negative stock is prevented."""
    sku = service.create_sku("Widget", 100)
    with pytest.raises(ValueError):
        service.adjust_stock(sku.id, -150)


def test_adjust_stock_nonexistent_sku(service):
    """Test adjusting stock for non-existent SKU."""
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock(999, 10)


def test_create_reservation_success(service):
    """Test creating a reservation with sufficient stock."""
    sku = service.create_sku("Widget", 100)
    reservation = service.create_reservation(sku.id, 50, "key-1")

    assert reservation.id is not None
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 50
    assert reservation.status == ReservationStatus.PENDING
    assert reservation.idempotency_key == "key-1"

    # Check that stock was reserved
    sku = service.repo.get_sku(sku.id)
    assert sku.available_stock == 50
    assert sku.reserved_stock == 50


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails with insufficient stock."""
    sku = service.create_sku("Widget", 50)
    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 100, "key-1")


def test_create_reservation_idempotency(service):
    """Test that idempotency keys return existing reservation."""
    sku = service.create_sku("Widget", 100)
    res1 = service.create_reservation(sku.id, 50, "key-1")
    res2 = service.create_reservation(sku.id, 50, "key-1")

    assert res1.id == res2.id
    # Stock should not be double-reserved
    sku = service.repo.get_sku(sku.id)
    assert sku.reserved_stock == 50


def test_create_reservation_nonexistent_sku(service):
    """Test reservation fails for non-existent SKU."""
    with pytest.raises(SKUNotFoundError):
        service.create_reservation(999, 10, "key-1")


def test_confirm_reservation_success(service):
    """Test confirming a pending reservation."""
    sku = service.create_sku("Widget", 100)
    reservation = service.create_reservation(sku.id, 50, "key-1")

    order = service.confirm_reservation(reservation.id)

    assert order.id is not None
    assert order.reservation_id == reservation.id
    assert order.sku_id == sku.id
    assert order.quantity == 50
    assert order.status == ReservationStatus.CONFIRMED

    # Verify reservation status changed
    updated = service.repo.get_reservation(reservation.id)
    assert updated.status == ReservationStatus.CONFIRMED


def test_confirm_reservation_expired(service):
    """Test confirming an expired reservation fails."""
    sku = service.create_sku("Widget", 100)
    reservation = service.create_reservation(sku.id, 50, "key-1")

    # Manually set expiration to past
    with service.repo._get_connection() as conn:
        past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        conn.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past, reservation.id),
        )
        conn.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    # Status should be marked as expired
    updated = service.repo.get_reservation(reservation.id)
    assert updated.status == ReservationStatus.EXPIRED


def test_confirm_reservation_nonexistent(service):
    """Test confirming non-existent reservation."""
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_confirm_reservation_already_confirmed(service):
    """Test confirming already confirmed reservation fails."""
    sku = service.create_sku("Widget", 100)
    reservation = service.create_reservation(sku.id, 50, "key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidReservationStateError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    """Test cancelling a pending reservation."""
    sku = service.create_sku("Widget", 100)
    reservation = service.create_reservation(sku.id, 50, "key-1")

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED

    # Check that stock was released
    sku = service.repo.get_sku(sku.id)
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_cancel_reservation_nonexistent(service):
    """Test cancelling non-existent reservation."""
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(999)


def test_cancel_reservation_confirmed_fails(service):
    """Test cancelling confirmed reservation fails."""
    sku = service.create_sku("Widget", 100)
    reservation = service.create_reservation(sku.id, 50, "key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation.id)


def test_get_orders_empty(service):
    """Test getting orders when none exist."""
    orders, next_cursor = service.get_orders()
    assert orders == []
    assert next_cursor is None


def test_get_orders_pagination(service):
    """Test pagination of orders."""
    sku = service.create_sku("Widget", 1000)

    # Create and confirm multiple reservations
    for i in range(25):
        res = service.create_reservation(sku.id, 10, f"key-{i}")
        service.confirm_reservation(res.id)

    # Get first page
    orders, next_cursor = service.get_orders(limit=10)
    assert len(orders) == 10
    assert next_cursor is not None

    # Get second page
    orders2, next_cursor2 = service.get_orders(limit=10, cursor=next_cursor)
    assert len(orders2) == 10
    assert next_cursor2 is not None

    # Get third page
    orders3, next_cursor3 = service.get_orders(limit=10, cursor=next_cursor2)
    assert len(orders3) == 5
    assert next_cursor3 is None
