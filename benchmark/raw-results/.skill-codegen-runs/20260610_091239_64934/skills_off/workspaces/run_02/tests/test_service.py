import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repository):
    return Service(repository)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", "Widget A")
    assert sku.sku_id == "SKU-001"
    assert sku.name == "Widget A"
    assert sku.available == 0
    assert sku.reserved == 0


def test_adjust_stock(service):
    service.create_sku("SKU-001", "Widget A")

    sku = service.adjust_stock("SKU-001", 100)
    assert sku.available == 100
    assert sku.reserved == 0

    sku = service.adjust_stock("SKU-001", -30)
    assert sku.available == 70
    assert sku.reserved == 0


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    assert reservation.sku_id == "SKU-001"
    assert reservation.quantity == 10
    assert reservation.status == ReservationStatus.PENDING

    sku = service.repo.get_sku("SKU-001")
    assert sku.available == 90
    assert sku.reserved == 10


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU-001", 10, "idempotency-key-1")


def test_create_reservation_idempotent_retry(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    res1 = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    res2 = service.create_reservation("SKU-001", 10, "idempotency-key-1")

    assert res1.reservation_id == res2.reservation_id

    sku = service.repo.get_sku("SKU-001")
    assert sku.available == 90
    assert sku.reserved == 10


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    order = service.confirm_reservation(reservation.reservation_id)

    assert order.sku_id == "SKU-001"
    assert order.quantity == 10
    assert order.reservation_id == reservation.reservation_id

    updated_reservation = service.repo.get_reservation(reservation.reservation_id)
    assert updated_reservation.status == ReservationStatus.CONFIRMED

    sku = service.repo.get_sku("SKU-001")
    assert sku.available == 90
    assert sku.reserved == 0


def test_confirm_reservation_already_confirmed(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    service.confirm_reservation(reservation.reservation_id)

    with pytest.raises(ReservationAlreadyConfirmedError):
        service.confirm_reservation(reservation.reservation_id)


def test_confirm_reservation_expired(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    service.repo.session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.reservation_id)


def test_cancel_reservation_happy_path(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 10, "idempotency-key-1")

    sku = service.repo.get_sku("SKU-001")
    assert sku.available == 90
    assert sku.reserved == 10

    cancelled = service.cancel_reservation(reservation.reservation_id)
    assert cancelled.status == ReservationStatus.CANCELLED

    sku = service.repo.get_sku("SKU-001")
    assert sku.available == 100
    assert sku.reserved == 0


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("non-existent-id")


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    for i in range(15):
        reservation = service.create_reservation("SKU-001", 1, f"idempotency-key-{i}")
        service.confirm_reservation(reservation.reservation_id)

    orders, total = service.get_orders(offset=0, limit=10)
    assert len(orders) == 10
    assert total == 15

    orders, total = service.get_orders(offset=10, limit=10)
    assert len(orders) == 5
    assert total == 15


def test_expire_reservations(service, repository):
    service.create_sku("SKU-001", "Widget A")
    service.adjust_stock("SKU-001", 100)

    res1 = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    res2 = service.create_reservation("SKU-001", 10, "idempotency-key-2")

    res1.expires_at = datetime.utcnow() - timedelta(seconds=1)
    res2.expires_at = datetime.utcnow() + timedelta(minutes=10)
    repository.session.commit()

    expired_count = service.expire_reservations()
    assert expired_count == 1

    updated_res1 = repository.get_reservation(res1.reservation_id)
    assert updated_res1.status == ReservationStatus.EXPIRED

    updated_res2 = repository.get_reservation(res2.reservation_id)
    assert updated_res2.status == ReservationStatus.PENDING
