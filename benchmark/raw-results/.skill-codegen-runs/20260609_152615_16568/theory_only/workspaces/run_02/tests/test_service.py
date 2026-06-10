"""Tests for the service layer."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.repository import Base, Repository
from commerce_service.service import (
    Service, ReservationExpiredError, InsufficientStockError,
    SKUNotFoundError, ReservationNotFoundError
)
from commerce_service.models import ReservationStatus


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    """Create a service instance with test database."""
    return Service(db)


def test_create_sku(service):
    """Test SKU creation."""
    sku = service.create_sku("SKU-001", "Test Product")
    assert sku.id is not None
    assert sku.code == "SKU-001"
    assert sku.name == "Test Product"
    assert sku.stock == 0
    assert sku.reserved == 0


def test_get_sku(service):
    """Test getting a SKU."""
    sku = service.create_sku("SKU-001", "Test Product")
    retrieved = service.get_sku(sku.id)
    assert retrieved.id == sku.id
    assert retrieved.code == "SKU-001"


def test_get_nonexistent_sku(service):
    """Test getting a nonexistent SKU raises error."""
    with pytest.raises(SKUNotFoundError):
        service.get_sku(999)


def test_adjust_stock(service):
    """Test stock adjustment."""
    sku = service.create_sku("SKU-001", "Test Product")
    adjusted = service.adjust_stock(sku.id, 100)
    assert adjusted.stock == 100

    adjusted = service.adjust_stock(sku.id, -30)
    assert adjusted.stock == 70


def test_adjust_stock_negative_fails(service):
    """Test that stock cannot go negative."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 10)
    with pytest.raises(ValueError):
        service.adjust_stock(sku.id, -20)


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )
    assert reservation.id is not None
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 50
    assert reservation.status == ReservationStatus.PENDING

    # Verify reserved count was updated
    updated_sku = service.get_sku(sku.id)
    assert updated_sku.reserved == 50
    assert updated_sku.available == 50


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails when stock is insufficient."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 30)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(
            sku_id=sku.id,
            quantity=50,
            idempotency_key="key-001"
        )


def test_create_reservation_idempotency(service):
    """Test that duplicate idempotency keys return existing reservation."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    res1 = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )

    res2 = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )

    assert res1.id == res2.id
    # Verify only one reservation was created
    updated_sku = service.get_sku(sku.id)
    assert updated_sku.reserved == 50


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )

    order = service.confirm_reservation(reservation.id)
    assert order.id is not None
    assert order.reservation_id == reservation.id
    assert order.status.value == "pending"

    # Verify reservation status was updated
    updated_res = service.get_reservation(reservation.id)
    assert updated_res.status == ReservationStatus.CONFIRMED


def test_confirm_expired_reservation(service):
    """Test that confirming an expired reservation fails."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )

    # Manually set expiration to past
    repo = Repository(service.repo.db)
    repo.db.query(repo.__class__.__bases__[0]).first()
    from commerce_service.repository import ReservationModel
    res_db = repo.db.query(ReservationModel).filter(
        ReservationModel.id == reservation.id
    ).first()
    res_db.expires_at = datetime.utcnow() - timedelta(hours=1)
    repo.db.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    # Verify reservation was cancelled and stock released
    updated_res = service.get_reservation(reservation.id)
    assert updated_res.status == ReservationStatus.CANCELLED
    updated_sku = service.get_sku(sku.id)
    assert updated_sku.reserved == 0


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED

    # Verify stock was released
    updated_sku = service.get_sku(sku.id)
    assert updated_sku.reserved == 0


def test_cancel_confirmed_reservation_fails(service):
    """Test that cancelling a confirmed reservation fails."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="key-001"
    )
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError):
        service.cancel_reservation(reservation.id)


def test_list_orders_with_pagination(service):
    """Test order listing with pagination."""
    sku = service.create_sku("SKU-001", "Test Product")
    service.adjust_stock(sku.id, 500)

    # Create and confirm multiple reservations
    for i in range(5):
        res = service.create_reservation(
            sku_id=sku.id,
            quantity=10,
            idempotency_key=f"key-{i:03d}"
        )
        service.confirm_reservation(res.id)

    # Test pagination
    items, total = service.list_orders(offset=0, limit=2)
    assert total == 5
    assert len(items) == 2

    items, total = service.list_orders(offset=2, limit=2)
    assert total == 5
    assert len(items) == 2

    items, total = service.list_orders(offset=4, limit=2)
    assert total == 5
    assert len(items) == 1
