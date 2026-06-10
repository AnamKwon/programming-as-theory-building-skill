"""Tests for service layer business logic."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.commerce_service.models import Base, OrderStatus, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommercService,
    ConflictError,
    NotFoundError,
    ValidationError,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def repo(db_session):
    """Create a repository instance."""
    return Repository(db_session)


@pytest.fixture
def service(repo):
    """Create a service instance."""
    return CommercService(repo)


def test_create_sku(service):
    """Test creating a new SKU."""
    sku = service.create_sku("PROD-001", "Test Product")
    assert sku.id == "PROD-001"
    assert sku.name == "Test Product"


def test_create_sku_duplicate(service):
    """Test that duplicate SKU creation fails."""
    service.create_sku("PROD-001", "Test Product")
    with pytest.raises(ConflictError):
        service.create_sku("PROD-001", "Another Product")


def test_get_sku_not_found(service):
    """Test getting a non-existent SKU."""
    with pytest.raises(NotFoundError):
        service.get_sku("NONEXISTENT")


def test_adjust_stock(service):
    """Test adjusting inventory stock."""
    service.create_sku("PROD-001", "Test Product")
    inventory = service.adjust_stock("PROD-001", 100)
    assert inventory.available_quantity == 100
    assert inventory.reserved_quantity == 0


def test_adjust_stock_negative_invalid(service):
    """Test that negative adjustment doesn't go below zero."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 50)
    with pytest.raises(ValidationError):
        service.adjust_stock("PROD-001", -100)


def test_create_reservation_insufficient_stock(service):
    """Test creating reservation with insufficient stock."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 10)

    with pytest.raises(ValidationError, match="Insufficient stock"):
        service.create_reservation(
            sku_id="PROD-001",
            order_id="ORDER-001",
            quantity=20,
        )


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 100)

    reservation = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-001",
        quantity=50,
    )
    assert reservation.status == ReservationStatus.PENDING
    assert reservation.quantity == 50
    assert reservation.sku_id == "PROD-001"
    assert reservation.order_id == "ORDER-001"

    # Verify inventory was reserved
    inventory = service.get_inventory("PROD-001")
    assert inventory.available_quantity == 50
    assert inventory.reserved_quantity == 50


def test_reservation_idempotency(service):
    """Test that idempotency keys return existing reservations."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 100)

    idempotency_key = str(uuid.uuid4())
    res1 = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-001",
        quantity=50,
        idempotency_key=idempotency_key,
    )

    # Same idempotency key should return the same reservation
    res2 = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-002",
        quantity=60,
        idempotency_key=idempotency_key,
    )
    assert res1.id == res2.id


def test_confirm_reservation(service):
    """Test confirming a pending reservation."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 100)

    reservation = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-001",
        quantity=50,
    )

    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == ReservationStatus.CONFIRMED

    # Verify order is also confirmed
    order = service.get_order("ORDER-001")
    assert order.status == OrderStatus.CONFIRMED


def test_confirm_expired_reservation(service):
    """Test that expired reservations cannot be confirmed."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 100)

    # Create reservation with 1 second TTL
    reservation = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-001",
        quantity=50,
        ttl_seconds=1,
    )

    # Wait for expiration (mock by manually setting time)
    import time
    time.sleep(1.1)

    with pytest.raises(ValidationError, match="has expired"):
        service.confirm_reservation(reservation.id)

    # Verify reservation is marked as expired
    updated = service.get_reservation(reservation.id)
    assert updated.status == ReservationStatus.EXPIRED


def test_cancel_pending_reservation(service):
    """Test cancelling a pending reservation."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 100)

    reservation = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-001",
        quantity=50,
    )

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED

    # Verify inventory is released
    inventory = service.get_inventory("PROD-001")
    assert inventory.available_quantity == 100
    assert inventory.reserved_quantity == 0


def test_cancel_confirmed_reservation_fails(service):
    """Test that confirmed reservations cannot be cancelled."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 100)

    reservation = service.create_reservation(
        sku_id="PROD-001",
        order_id="ORDER-001",
        quantity=50,
    )
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValidationError, match="Cannot cancel confirmed"):
        service.cancel_reservation(reservation.id)


def test_list_orders_pagination(service):
    """Test order listing with pagination."""
    service.create_sku("PROD-001", "Test Product")
    service.adjust_stock("PROD-001", 1000)

    # Create multiple reservations
    for i in range(25):
        service.create_reservation(
            sku_id="PROD-001",
            order_id=f"ORDER-{i:03d}",
            quantity=10,
        )

    # Test first page
    result = service.list_orders(page=1, page_size=10)
    assert len(result["orders"]) == 10
    assert result["total"] == 25
    assert result["page"] == 1
    assert result["has_more"] is True

    # Test second page
    result = service.list_orders(page=2, page_size=10)
    assert len(result["orders"]) == 10
    assert result["page"] == 2
    assert result["has_more"] is True

    # Test last page
    result = service.list_orders(page=3, page_size=10)
    assert len(result["orders"]) == 5
    assert result["page"] == 3
    assert result["has_more"] is False
