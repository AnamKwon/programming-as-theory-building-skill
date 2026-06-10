import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    repo = Repository(db_session)
    return Service(repo)


def test_create_sku(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    assert sku.sku_code == "SKU001"
    assert sku.name == "Test Product"
    assert sku.quantity == 100


def test_adjust_stock_increase(service):
    sku = service.create_sku("SKU001", "Test Product", 50)
    updated = service.adjust_stock(sku.id, 25)
    assert updated.quantity == 75


def test_adjust_stock_decrease(service):
    sku = service.create_sku("SKU001", "Test Product", 50)
    updated = service.adjust_stock(sku.id, -25)
    assert updated.quantity == 25


def test_adjust_stock_negative_fails(service):
    sku = service.create_sku("SKU001", "Test Product", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.adjust_stock(sku.id, -100)


def test_create_reservation_success(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation(sku.id, 50)
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 50
    assert reservation.state == ReservationState.PENDING
    assert sku.id == reservation.sku_id


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU001", "Test Product", 30)
    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 50)


def test_create_reservation_idempotent(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    idempotency_key = "idem-123"
    res1 = service.create_reservation(sku.id, 50, idempotency_key=idempotency_key)
    res2 = service.create_reservation(sku.id, 50, idempotency_key=idempotency_key)
    assert res1.id == res2.id


def test_create_reservation_reserves_stock(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    service.create_reservation(sku.id, 50)
    repo = Repository(service.repo.db)
    updated_sku = repo.get_sku(sku.id)
    assert updated_sku.quantity == 50


def test_confirm_reservation_success(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation(sku.id, 50)
    order = service.confirm_reservation(reservation.id)
    assert order.reservation_id == reservation.id
    assert order.state == "confirmed"


def test_confirm_expired_reservation(service, db_session):
    sku = service.create_sku("SKU001", "Test Product", 100)
    repo = Repository(db_session)
    expires_at = datetime.utcnow() - timedelta(minutes=1)
    reservation = repo.create_reservation(sku.id, 50, expires_at)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation(sku.id, 50)
    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.state == ReservationState.CANCELLED


def test_cancel_reservation_restores_stock(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation(sku.id, 50)
    service.cancel_reservation(reservation.id)

    repo = Repository(service.repo.db)
    updated_sku = repo.get_sku(sku.id)
    assert updated_sku.quantity == 100


def test_cancel_confirmed_reservation_fails(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation(sku.id, 50)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(reservation.id)


def test_cancel_idempotent(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation(sku.id, 50)
    service.cancel_reservation(reservation.id)
    cancelled_again = service.cancel_reservation(reservation.id)
    assert cancelled_again.state == ReservationState.CANCELLED


def test_get_orders_pagination(service):
    sku = service.create_sku("SKU001", "Test Product", 1000)
    for i in range(25):
        res = service.create_reservation(sku.id, 10)
        service.confirm_reservation(res.id)

    orders, total = service.get_orders(limit=10, offset=0)
    assert len(orders) == 10
    assert total == 25

    orders2, total2 = service.get_orders(limit=10, offset=10)
    assert len(orders2) == 10
    assert total2 == 25
