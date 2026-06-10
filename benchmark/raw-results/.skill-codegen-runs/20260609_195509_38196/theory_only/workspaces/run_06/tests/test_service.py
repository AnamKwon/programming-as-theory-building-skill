"""Unit tests for service layer business logic."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    InsufficientStockError,
    OrderService,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite session for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create OrderService with test session."""
    repo = Repository(db_session)
    return OrderService(repo)


def test_create_sku(service, db_session):
    """Test SKU creation."""
    sku = service.create_sku("sku123", "Test Product")
    assert sku.sku_id == "sku123"
    assert sku.name == "Test Product"

    details = service.get_sku_details("sku123")
    assert details["available_quantity"] == 0
    assert details["reserved_quantity"] == 0


def test_adjust_stock(service, db_session):
    """Test stock adjustment."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 100, "adj_1")

    details = service.get_sku_details("sku123")
    assert details["available_quantity"] == 100

    service.adjust_stock("sku123", -30, "adj_2")
    details = service.get_sku_details("sku123")
    assert details["available_quantity"] == 70


def test_adjust_stock_sku_not_found(service):
    """Test stock adjustment fails when SKU doesn't exist."""
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("nonexistent", 10, "adj_1")


def test_create_reservation_happy_path(service, db_session):
    """Test reservation creation with sufficient stock."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 100, "adj_1")

    res_id = service.create_reservation("sku123", 50, "idempotency_key_1", ttl_seconds=1800)
    assert res_id.startswith("res_")

    details = service.get_reservation_details(res_id)
    assert details["status"] == ReservationStatus.PENDING
    assert details["quantity"] == 50
    assert details["sku_id"] == "sku123"

    # Check stock is reserved
    sku_details = service.get_sku_details("sku123")
    assert sku_details["available_quantity"] == 50
    assert sku_details["reserved_quantity"] == 50


def test_create_reservation_insufficient_stock(service, db_session):
    """Test reservation creation fails with insufficient stock."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 30, "adj_1")

    with pytest.raises(InsufficientStockError):
        service.create_reservation("sku123", 50, "idempotency_key_1")


def test_create_reservation_sku_not_found(service):
    """Test reservation creation fails when SKU doesn't exist."""
    with pytest.raises(SKUNotFoundError):
        service.create_reservation("nonexistent", 10, "idempotency_key_1")


def test_create_reservation_idempotency(service, db_session):
    """Test idempotent reservation creation."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 100, "adj_1")

    res_id_1 = service.create_reservation("sku123", 50, "unique_key_1", ttl_seconds=1800)

    # Same idempotency key should return same reservation
    res_id_2 = service.create_reservation("sku123", 50, "unique_key_1", ttl_seconds=1800)
    assert res_id_1 == res_id_2

    # Stock should not be double-reserved
    sku_details = service.get_sku_details("sku123")
    assert sku_details["reserved_quantity"] == 50


def test_confirm_reservation_happy_path(service, db_session):
    """Test reservation confirmation into order."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 100, "adj_1")

    res_id = service.create_reservation("sku123", 50, "idempotency_key_1", ttl_seconds=1800)
    db_session.commit()

    order_id = service.confirm_reservation(res_id)
    db_session.commit()

    assert order_id.startswith("ord_")

    # Check reservation is confirmed
    res_details = service.get_reservation_details(res_id)
    assert res_details["status"] == ReservationStatus.CONFIRMED

    # Check order exists
    order_details = service.get_order_details(order_id)
    assert order_details["quantity"] == 50
    assert order_details["reservation_id"] == res_id

    # Check stock is deducted (no longer reserved)
    sku_details = service.get_sku_details("sku123")
    assert sku_details["available_quantity"] == 50
    assert sku_details["reserved_quantity"] == 0


def test_confirm_reservation_expired(service, db_session):
    """Test confirmation fails for expired reservation."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 100, "adj_1")

    # Create reservation with very short TTL
    res_id = service.create_reservation("sku123", 50, "idempotency_key_1", ttl_seconds=1)
    db_session.commit()

    # Wait for expiration
    import time
    time.sleep(2)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(res_id)


def test_confirm_reservation_not_found(service):
    """Test confirmation fails for nonexistent reservation."""
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("res_nonexistent")


def test_cancel_reservation(service, db_session):
    """Test reservation cancellation and stock release."""
    service.create_sku("sku123", "Product")
    service.adjust_stock("sku123", 100, "adj_1")

    res_id = service.create_reservation("sku123", 50, "idempotency_key_1", ttl_seconds=1800)
    db_session.commit()

    service.cancel_reservation(res_id)
    db_session.commit()

    # Check reservation is cancelled
    res_details = service.get_reservation_details(res_id)
    assert res_details["status"] == ReservationStatus.CANCELLED

    # Check stock is released
    sku_details = service.get_sku_details("sku123")
    assert sku_details["available_quantity"] == 100
    assert sku_details["reserved_quantity"] == 0


def test_cancel_reservation_not_found(service):
    """Test cancellation fails for nonexistent reservation."""
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("res_nonexistent")


def test_reservation_workflow_full_cycle(service, db_session):
    """Test complete workflow: create SKU -> stock -> reserve -> confirm -> order."""
    # Create two SKUs
    service.create_sku("sku_a", "Product A")
    service.create_sku("sku_b", "Product B")

    # Add stock
    service.adjust_stock("sku_a", 100, "adj_1")
    service.adjust_stock("sku_b", 50, "adj_2")

    # Create two reservations
    res_1 = service.create_reservation("sku_a", 30, "key_1", ttl_seconds=1800)
    res_2 = service.create_reservation("sku_b", 20, "key_2", ttl_seconds=1800)
    db_session.commit()

    # Confirm first reservation
    order_1 = service.confirm_reservation(res_1)
    db_session.commit()

    assert order_1.startswith("ord_")

    # Verify stock state
    a_details = service.get_sku_details("sku_a")
    assert a_details["available_quantity"] == 70
    assert a_details["reserved_quantity"] == 0

    b_details = service.get_sku_details("sku_b")
    assert b_details["available_quantity"] == 30
    assert b_details["reserved_quantity"] == 20

    # List orders
    orders, total = service.list_orders(limit=10, offset=0)
    assert total == 1
    assert len(orders) == 1
    assert orders[0]["order_id"] == order_1
