"""Service layer tests."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    """Create test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(test_db):
    """Create service instance."""
    return CommerceService(test_db)


def test_create_sku(service):
    """Test SKU creation."""
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku == "SKU-001"
    assert sku.available_stock == 100


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("SKU-001", 100)
    updated = service.adjust_stock("SKU-001", -10)
    assert updated.available_stock == 90

    updated = service.adjust_stock("SKU-001", 20)
    assert updated.available_stock == 110


def test_adjust_stock_nonexistent(service):
    """Test adjusting stock for non-existent SKU."""
    with pytest.raises(ValueError, match="SKU .* not found"):
        service.adjust_stock("SKU-MISSING", 10)


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idempotency-1")
    assert reservation.id is not None
    assert reservation.sku == "SKU-001"
    assert reservation.quantity == 10
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-1"

    # Check stock was deducted
    sku = service.sku_repo.get_sku("SKU-001")
    assert sku.available_stock == 90


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("SKU-001", 100)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 150, "idempotency-1")


def test_create_reservation_idempotency(service):
    """Test idempotent reservation creation."""
    service.create_sku("SKU-001", 100)
    reservation1 = service.create_reservation("SKU-001", 10, "idempotency-1")
    reservation2 = service.create_reservation("SKU-001", 10, "idempotency-1")

    assert reservation1.id == reservation2.id
    assert reservation1.idempotency_key == reservation2.idempotency_key

    # Check stock was deducted only once
    sku = service.sku_repo.get_sku("SKU-001")
    assert sku.available_stock == 90


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idempotency-1")
    order = service.confirm_reservation(reservation.id)

    assert order.id is not None
    assert order.reservation_id == reservation.id
    assert order.sku == "SKU-001"
    assert order.quantity == 10

    # Check reservation status updated
    updated_reservation = service.reservation_repo.get_reservation(reservation.id)
    assert updated_reservation.status == "CONFIRMED"


def test_confirm_reservation_invalid_state(service):
    """Test confirming reservation not in PENDING state."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idempotency-1")
    service.confirm_reservation(reservation.id)

    # Try to confirm again
    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_expired(service, test_db):
    """Test confirming expired reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idempotency-1")

    # Manually set created_at to 301 seconds ago
    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = old_time.replace(tzinfo=None)
    test_db.commit()

    with pytest.raises(ValueError, match="Reservation expired"):
        service.confirm_reservation(reservation.id)

    # Check reservation status is EXPIRED
    updated_reservation = service.reservation_repo.get_reservation(reservation.id)
    assert updated_reservation.status == "EXPIRED"

    # Check stock was restored
    sku = service.sku_repo.get_sku("SKU-001")
    assert sku.available_stock == 100


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idempotency-1")
    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == "CANCELLED"

    # Check stock was restored
    sku = service.sku_repo.get_sku("SKU-001")
    assert sku.available_stock == 100


def test_cancel_reservation_invalid_state(service):
    """Test cancelling reservation not in PENDING state."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idempotency-1")
    service.confirm_reservation(reservation.id)

    # Try to cancel confirmed reservation
    with pytest.raises(ValueError, match="not in PENDING state"):
        service.cancel_reservation(reservation.id)


def test_get_orders_pagination(service):
    """Test orders pagination."""
    service.create_sku("SKU-001", 1000)

    # Create multiple orders
    for i in range(25):
        reservation = service.create_reservation("SKU-001", 10, f"idempotency-{i}")
        service.confirm_reservation(reservation.id)

    # Test first page
    orders, total = service.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 25

    # Test second page
    orders, total = service.get_orders(page=2, size=10)
    assert len(orders) == 10
    assert total == 25

    # Test third page
    orders, total = service.get_orders(page=3, size=10)
    assert len(orders) == 5
    assert total == 25
