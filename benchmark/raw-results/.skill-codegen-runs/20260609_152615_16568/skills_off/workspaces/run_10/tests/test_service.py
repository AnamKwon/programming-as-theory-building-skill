import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, RESERVATION_TTL_SECONDS
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    InvalidStateTransitionError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repository(db):
    return Repository(db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    sku = service.create_sku("SKU-001")
    assert sku.sku_code == "SKU-001"
    assert sku.stock_available == 0


def test_adjust_stock(service):
    sku = service.create_sku("SKU-001")
    updated = service.adjust_stock(sku.id, 100)
    assert updated.stock_available == 100

    updated = service.adjust_stock(sku.id, -30)
    assert updated.stock_available == 70


def test_adjust_stock_not_found(service):
    with pytest.raises(ValueError, match="SKU 999 not found"):
        service.adjust_stock(999, 10)


def test_create_reservation_success(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 50)
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 50
    assert reservation.status.value == "pending"


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 30)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 50)


def test_create_reservation_idempotency(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)

    key = "idempotency-123"
    res1 = service.create_reservation(sku.id, 50, idempotency_key=key)
    res2 = service.create_reservation(sku.id, 50, idempotency_key=key)

    assert res1.id == res2.id


def test_confirm_reservation_success(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50)

    res, order = service.confirm_reservation(reservation.id)
    assert res.status.value == "confirmed"
    assert order.id is not None
    assert order.status.value == "pending"

    updated_sku = service.repo.get_sku(sku.id)
    assert updated_sku.stock_available == 50


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_confirm_reservation_expired(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50)

    expired_time = datetime.utcnow() - timedelta(seconds=100)
    service.repo.db.query(type(reservation)).filter(
        type(reservation).id == reservation.id
    ).update({"expires_at": expired_time})
    service.repo.db.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)
    res1 = service.create_reservation(sku.id, 60)
    res2 = service.create_reservation(sku.id, 50)

    service.confirm_reservation(res1.id)
    with pytest.raises(InsufficientStockError):
        service.confirm_reservation(res2.id)


def test_confirm_already_confirmed_reservation(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50)

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status.value == "cancelled"


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(999)


def test_cancel_confirmed_reservation(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(reservation.id)


def test_list_orders(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 300)

    for i in range(5):
        res = service.create_reservation(sku.id, 10)
        service.confirm_reservation(res.id)

    orders, total = service.list_orders(offset=0, limit=10)
    assert len(orders) == 5
    assert total == 5


def test_list_orders_pagination(service):
    sku = service.create_sku("SKU-001")
    service.adjust_stock(sku.id, 300)

    for i in range(25):
        res = service.create_reservation(sku.id, 10)
        service.confirm_reservation(res.id)

    page1, total = service.list_orders(offset=0, limit=10)
    page2, _ = service.list_orders(offset=10, limit=10)
    page3, _ = service.list_orders(offset=20, limit=10)

    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5
    assert total == 25
