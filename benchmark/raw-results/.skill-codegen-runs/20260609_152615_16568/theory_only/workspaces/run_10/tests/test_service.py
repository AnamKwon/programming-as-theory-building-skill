"""Tests for service layer business logic."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.repository import Base, Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    ReservationNotFoundError,
)
from commerce_service.models import ReservationStatus, OrderStatus


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    repo = Repository(db_session)
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("WIDGET-001", "Blue Widget", 100)
    assert result.sku_code == "WIDGET-001"
    assert result.name == "Blue Widget"
    assert result.stock_count == 100


def test_adjust_stock(service):
    sku = service.create_sku("GADGET-001", "Red Gadget", 50)
    result = service.adjust_stock(sku.id, 25)
    assert result.stock_count == 75

    result = service.adjust_stock(sku.id, -10)
    assert result.stock_count == 65


def test_reserve_stock_happy_path(service):
    sku = service.create_sku("WIDGET-002", "Green Widget", 100)
    reservation = service.reserve_stock(sku.id, 10)

    assert reservation.status == ReservationStatus.PENDING
    assert reservation.quantity == 10
    assert reservation.sku_id == sku.id
    assert reservation.order_id is None


def test_reserve_stock_insufficient(service):
    sku = service.create_sku("WIDGET-003", "Yellow Widget", 10)
    with pytest.raises(InsufficientStockError):
        service.reserve_stock(sku.id, 20)


def test_reserve_stock_exact_quantity(service):
    sku = service.create_sku("WIDGET-004", "Purple Widget", 50)
    reservation = service.reserve_stock(sku.id, 50)
    assert reservation.quantity == 50


def test_reserve_stock_idempotent(service):
    sku = service.create_sku("WIDGET-005", "Orange Widget", 100)
    key = "unique-request-1"

    res1 = service.reserve_stock(sku.id, 15, idempotency_key=key)
    res2 = service.reserve_stock(sku.id, 15, idempotency_key=key)

    assert res1.id == res2.id
    assert res1.status == res2.status


def test_reserve_stock_idempotent_retry_expired(service):
    sku = service.create_sku("WIDGET-006", "Pink Widget", 100)
    key = "expired-key"

    reservation = service.reserve_stock(sku.id, 10, idempotency_key=key)
    service.repo.update_reservation_status(reservation.id, ReservationStatus.EXPIRED)

    with pytest.raises(ReservationExpiredError):
        service.reserve_stock(sku.id, 10, idempotency_key=key)


def test_confirm_reservation(service):
    sku = service.create_sku("WIDGET-007", "Cyan Widget", 100)
    reservation = service.reserve_stock(sku.id, 20)

    order = service.confirm_reservation(reservation.id)

    assert order.status == OrderStatus.CONFIRMED
    updated_res = service.repo.get_reservation(reservation.id)
    assert updated_res.status == ReservationStatus.CONFIRMED
    assert updated_res.order_id == order.id


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_confirm_reservation_expired(service):
    from commerce_service.repository import Reservation

    sku = service.create_sku("WIDGET-008", "Gray Widget", 100)
    reservation = service.reserve_stock(sku.id, 10)

    past_time = datetime.utcnow() - timedelta(minutes=1)
    service.repo.session.query(Reservation).filter(
        Reservation.id == reservation.id
    ).update({"expires_at": past_time})
    service.repo.session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_already_confirmed(service):
    sku = service.create_sku("WIDGET-009", "Brown Widget", 100)
    reservation = service.reserve_stock(sku.id, 10)

    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(service):
    sku = service.create_sku("WIDGET-010", "Magenta Widget", 100)
    reservation = service.reserve_stock(sku.id, 30)

    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == ReservationStatus.CANCELLED
    updated_sku = service.repo.get_sku(sku.id)
    assert updated_sku.stock_count == 100


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(999)


def test_cancel_reservation_confirmed(service):
    sku = service.create_sku("WIDGET-011", "Teal Widget", 100)
    reservation = service.reserve_stock(sku.id, 10)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(reservation.id)


def test_list_orders_empty(service):
    orders, total = service.list_orders(offset=0, limit=20)
    assert orders == []
    assert total == 0


def test_list_orders_pagination(service):
    sku = service.create_sku("WIDGET-012", "Lime Widget", 1000)

    order_ids = []
    for i in range(5):
        reservation = service.reserve_stock(sku.id, 10)
        order = service.confirm_reservation(reservation.id)
        order_ids.append(order.id)

    all_orders, total = service.list_orders(offset=0, limit=20)
    assert len(all_orders) == 5
    assert total == 5

    page1, _ = service.list_orders(offset=0, limit=2)
    page2, _ = service.list_orders(offset=2, limit=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


def test_stock_reserved_not_available(service):
    sku = service.create_sku("WIDGET-013", "Navy Widget", 100)
    service.reserve_stock(sku.id, 60)

    with pytest.raises(InsufficientStockError):
        service.reserve_stock(sku.id, 50)


def test_reservation_expiry_check(service):
    from commerce_service.repository import Reservation

    sku = service.create_sku("WIDGET-014", "Maroon Widget", 100)
    reservation = service.reserve_stock(sku.id, 10)

    past_time = datetime.utcnow() - timedelta(minutes=1)
    service.repo.session.query(Reservation).filter(
        Reservation.id == reservation.id
    ).update({"expires_at": past_time})
    service.repo.session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)
