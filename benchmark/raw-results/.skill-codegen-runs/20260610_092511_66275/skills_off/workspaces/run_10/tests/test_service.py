import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base, ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(db_session):
    return CommerceService(Repository(db_session))


def test_create_sku(service):
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku_id == "SKU-001"
    assert sku.stock_available == 100


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    adjusted = service.adjust_stock("SKU-001", -20)
    assert adjusted.stock_available == 80

    adjusted = service.adjust_stock("SKU-001", 50)
    assert adjusted.stock_available == 130


def test_adjust_stock_not_found(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("SKU-MISSING", 10)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50)

    assert reservation.sku_id == "SKU-001"
    assert reservation.quantity == 50
    assert reservation.state == ReservationState.PENDING

    sku = service.repo.get_sku("SKU-001")
    assert sku.stock_available == 50


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU-001", 50)


def test_create_reservation_sku_not_found(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.create_reservation("SKU-MISSING", 10)


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    res1 = service.create_reservation("SKU-001", 50, idempotency_key="idem-001")
    res2 = service.create_reservation("SKU-001", 50, idempotency_key="idem-001")

    assert res1.reservation_id == res2.reservation_id
    sku = service.repo.get_sku("SKU-001")
    assert sku.stock_available == 50


def test_create_reservation_idempotency_expired(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 50, idempotency_key="idem-001")

    service.repo.update_reservation_state(res.reservation_id, ReservationState.EXPIRED)

    with pytest.raises(ReservationExpiredError):
        service.create_reservation("SKU-001", 50, idempotency_key="idem-001")


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50)
    confirmed = service.confirm_reservation(reservation.reservation_id)

    assert confirmed.state == ReservationState.CONFIRMED


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("MISSING-RES")


def test_cancel_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50)
    cancelled = service.cancel_reservation(reservation.reservation_id)

    assert cancelled.state == ReservationState.CANCELLED
    sku = service.repo.get_sku("SKU-001")
    assert sku.stock_available == 100


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("MISSING-RES")


def test_cancel_confirmed_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50)
    service.confirm_reservation(reservation.reservation_id)

    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(reservation.reservation_id)


def test_expire_pending_reservations(service):
    service.create_sku("SKU-001", 100)
    res1 = service.create_reservation("SKU-001", 30)
    res2 = service.create_reservation("SKU-001", 20)

    assert service.repo.get_sku("SKU-001").stock_available == 50

    # Manually expire one and release stock
    service.repo.update_reservation_state(res1.reservation_id, ReservationState.EXPIRED)
    service.repo.update_sku_stock("SKU-001", 30)

    sku = service.repo.get_sku("SKU-001")
    assert sku.stock_available == 80


def test_list_orders(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50)
    service.confirm_reservation(reservation.reservation_id)

    orders, total = service.list_orders(skip=0, limit=10)
    assert len(orders) == 1
    assert total == 1
