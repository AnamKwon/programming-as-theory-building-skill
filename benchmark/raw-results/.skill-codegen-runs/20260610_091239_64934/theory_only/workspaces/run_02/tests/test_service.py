import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
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
    return CommerceService(db_session)


def test_create_sku(service):
    sku = service.create_sku("sku-001", "Widget", initial_stock=100)
    assert sku.id == "sku-001"
    assert sku.name == "Widget"
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_create_duplicate_sku_fails(service):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("sku-001", "Widget", initial_stock=50)


def test_adjust_stock(service):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    sku = service.adjust_stock("sku-001", 50)
    assert sku.available_stock == 150


def test_adjust_stock_nonexistent_sku_fails(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock("sku-nonexistent", 10)


def test_create_reservation_happy_path(service):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    reservation = service.create_reservation("sku-001", 10)

    assert reservation.sku_id == "sku-001"
    assert reservation.quantity == 10
    assert reservation.status == ReservationStatus.ACTIVE

    sku = service.sku_repo.get_by_id("sku-001")
    assert sku.available_stock == 90
    assert sku.reserved_stock == 10


def test_create_reservation_insufficient_stock(service):
    service.create_sku("sku-001", "Widget", initial_stock=5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation("sku-001", 10)


def test_create_reservation_nonexistent_sku_fails(service):
    with pytest.raises(ValueError, match="not found"):
        service.create_reservation("sku-nonexistent", 10)


def test_confirm_reservation_happy_path(service):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    reservation = service.create_reservation("sku-001", 10)

    order = service.confirm_reservation(reservation.id)

    assert order.sku_id == "sku-001"
    assert order.quantity == 10
    assert order.status == OrderStatus.CONFIRMED
    assert order.reservation_id == reservation.id

    updated_reservation = service.reservation_repo.get_by_id(reservation.id)
    assert updated_reservation.status == ReservationStatus.CONFIRMED


def test_confirm_reservation_nonexistent_fails(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("nonexistent-id")


def test_confirm_expired_reservation_fails(service, db_session):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    reservation = service.create_reservation("sku-001", 10)

    expired_time = datetime.utcnow() - timedelta(minutes=1)
    reservation_record = service.reservation_repo.get_by_id(reservation.id)
    reservation_record.expires_at = expired_time
    db_session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    updated = service.reservation_repo.get_by_id(reservation.id)
    assert updated.status == ReservationStatus.EXPIRED


def test_cancel_reservation_happy_path(service):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    reservation = service.create_reservation("sku-001", 10)

    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == ReservationStatus.CANCELLED

    sku = service.sku_repo.get_by_id("sku-001")
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_cancel_reservation_nonexistent_fails(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("nonexistent-id")


def test_cancel_non_active_reservation_fails(service):
    service.create_sku("sku-001", "Widget", initial_stock=100)
    reservation = service.create_reservation("sku-001", 10)

    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="Cannot cancel"):
        service.cancel_reservation(reservation.id)


def test_list_orders_pagination(service):
    service.create_sku("sku-001", "Widget", initial_stock=1000)

    for i in range(25):
        reservation = service.create_reservation("sku-001", 5)
        service.confirm_reservation(reservation.id)

    orders, total = service.list_orders(offset=0, limit=10)
    assert len(orders) == 10
    assert total == 25

    orders_page2, total = service.list_orders(offset=10, limit=10)
    assert len(orders_page2) == 10
    assert total == 25

    orders_page3, total = service.list_orders(offset=20, limit=10)
    assert len(orders_page3) == 5
    assert total == 25


def test_cleanup_expired_reservations(service, db_session):
    service.create_sku("sku-001", "Widget", initial_stock=100)

    res1 = service.create_reservation("sku-001", 10)
    expired_time = datetime.utcnow() - timedelta(minutes=1)
    res1_record = service.reservation_repo.get_by_id(res1.id)
    res1_record.expires_at = expired_time
    db_session.commit()

    res2 = service.create_reservation("sku-001", 5)

    res1_updated = service.reservation_repo.get_by_id(res1.id)
    assert res1_updated.status == ReservationStatus.EXPIRED

    res2_updated = service.reservation_repo.get_by_id(res2.id)
    assert res2_updated.status == ReservationStatus.ACTIVE

    sku = service.sku_repo.get_by_id("sku-001")
    assert sku.available_stock == 95
    assert sku.reserved_stock == 5
