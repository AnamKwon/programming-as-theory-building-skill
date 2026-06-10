"""Service layer tests."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.service import CommerceService, CommerceProblem


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create a service instance."""
    return CommerceService(db_session)


def test_create_sku(service):
    """Test SKU creation."""
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku_code == "SKU-001"
    assert sku.stock_available == 100


def test_create_duplicate_sku_raises_error(service):
    """Test that duplicate SKU codes raise an error."""
    service.create_sku("SKU-001", 100)
    with pytest.raises(CommerceProblem) as exc_info:
        service.create_sku("SKU-001", 50)
    assert exc_info.value.status_code == 409


def test_adjust_stock(service):
    """Test stock adjustment."""
    sku = service.create_sku("SKU-002", 100)
    adjusted = service.adjust_stock(sku.id, 50)
    assert adjusted.stock_available == 150

    adjusted = service.adjust_stock(sku.id, -30)
    assert adjusted.stock_available == 120


def test_adjust_stock_below_zero_raises_error(service):
    """Test that adjusting stock below zero raises an error."""
    sku = service.create_sku("SKU-003", 50)
    with pytest.raises(CommerceProblem) as exc_info:
        service.adjust_stock(sku.id, -60)
    assert exc_info.value.status_code == 400


def test_adjust_nonexistent_sku_raises_error(service):
    """Test that adjusting nonexistent SKU raises an error."""
    with pytest.raises(CommerceProblem) as exc_info:
        service.adjust_stock(999, 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    sku = service.create_sku("SKU-004", 100)
    reservation = service.create_reservation(sku.id, 30, "idempotency-key-1", 300)
    assert reservation.quantity == 30
    assert reservation.status == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    sku = service.create_sku("SKU-005", 50)
    with pytest.raises(CommerceProblem) as exc_info:
        service.create_reservation(sku.id, 100, "idempotency-key-2", 300)
    assert exc_info.value.status_code == 400


def test_create_reservation_idempotent(service):
    """Test that creating reservation with same idempotency key returns existing."""
    sku = service.create_sku("SKU-006", 100)
    res1 = service.create_reservation(sku.id, 30, "idempotency-key-3", 300)
    res2 = service.create_reservation(sku.id, 30, "idempotency-key-3", 300)
    assert res1.id == res2.id


def test_create_reservation_idempotent_with_cancelled_raises_error(service):
    """Test that reusing cancelled reservation's idempotency key raises error."""
    sku = service.create_sku("SKU-007", 100)
    res = service.create_reservation(sku.id, 30, "idempotency-key-4", 300)
    service.cancel_reservation(res.id)

    with pytest.raises(CommerceProblem) as exc_info:
        service.create_reservation(sku.id, 30, "idempotency-key-4", 300)
    assert exc_info.value.status_code == 409


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    sku = service.create_sku("SKU-008", 100)
    reservation = service.create_reservation(sku.id, 30, "idempotency-key-5", 300)
    confirmed_res, order = service.confirm_reservation(reservation.id)
    assert confirmed_res.status == ReservationStatus.CONFIRMED
    assert order.status == OrderStatus.PENDING


def test_confirm_nonexistent_reservation_raises_error(service):
    """Test confirming nonexistent reservation raises error."""
    with pytest.raises(CommerceProblem) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_confirm_already_confirmed_reservation_raises_error(service):
    """Test confirming already confirmed reservation raises error."""
    sku = service.create_sku("SKU-009", 100)
    reservation = service.create_reservation(sku.id, 30, "idempotency-key-6", 300)
    service.confirm_reservation(reservation.id)

    with pytest.raises(CommerceProblem) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_confirm_expired_reservation_raises_error(service, db_session):
    """Test confirming expired reservation raises error."""
    sku = service.create_sku("SKU-010", 100)
    # Create reservation that's already expired
    reservation = service.create_reservation(sku.id, 30, "idempotency-key-7", -1)

    with pytest.raises(CommerceProblem) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    sku = service.create_sku("SKU-011", 100)
    reservation = service.create_reservation(sku.id, 30, "idempotency-key-8", 300)
    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED


def test_cancel_nonexistent_reservation_raises_error(service):
    """Test cancelling nonexistent reservation raises error."""
    with pytest.raises(CommerceProblem) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404


def test_get_order_success(service):
    """Test getting an order."""
    sku = service.create_sku("SKU-012", 100)
    reservation = service.create_reservation(sku.id, 30, "idempotency-key-9", 300)
    _, order = service.confirm_reservation(reservation.id)

    retrieved_order = service.get_order(order.id)
    assert retrieved_order.id == order.id


def test_get_nonexistent_order_raises_error(service):
    """Test getting nonexistent order raises error."""
    with pytest.raises(CommerceProblem) as exc_info:
        service.get_order(999)
    assert exc_info.value.status_code == 404


def test_list_orders_pagination(service):
    """Test order listing with pagination."""
    sku = service.create_sku("SKU-013", 100)
    for i in range(5):
        reservation = service.create_reservation(sku.id, 10, f"idempotency-key-{i}", 300)
        service.confirm_reservation(reservation.id)

    orders, total = service.list_orders(offset=0, limit=2)
    assert len(orders) == 2
    assert total == 5

    orders, total = service.list_orders(offset=2, limit=2)
    assert len(orders) == 2

    orders, total = service.list_orders(offset=4, limit=2)
    assert len(orders) == 1
