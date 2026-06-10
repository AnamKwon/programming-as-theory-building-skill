import pytest
import os
import tempfile
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    ServiceValidationError,
)


@pytest.fixture
def db_file():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def db(db_file):
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def service(repo):
    return Service(repo)


def test_create_sku(service):
    sku = service.create_sku("PROD-001", 100)
    assert sku.sku == "PROD-001"
    assert sku.stock == 100
    assert sku.reserved == 0
    assert sku.available == 100


def test_create_sku_duplicate_fails(service):
    service.create_sku("PROD-001", 100)
    with pytest.raises(ServiceValidationError, match="already exists"):
        service.create_sku("PROD-001", 50)


def test_adjust_stock(service, repo):
    sku = service.create_sku("PROD-001", 100)
    adjusted = service.adjust_stock(sku.id, 50)
    assert adjusted.stock == 150
    adjusted = service.adjust_stock(sku.id, -30)
    assert adjusted.stock == 120


def test_adjust_stock_negative_fails(service, repo):
    sku = service.create_sku("PROD-001", 100)
    with pytest.raises(ServiceValidationError, match="cannot be negative"):
        service.adjust_stock(sku.id, -150)


def test_create_reservation_success(service, repo):
    sku = service.create_sku("PROD-001", 100)
    reservation = service.create_reservation(sku.id, 10, "idempotency-key-1")
    assert reservation.quantity == 10
    assert reservation.status == ReservationStatus.PENDING
    assert reservation.order_id is not None

    # Check stock was reserved
    updated_sku = repo.get_sku_by_id(sku.id)
    assert updated_sku.reserved == 10
    assert updated_sku.available == 90


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("PROD-001", 10)
    with pytest.raises(InsufficientStockError, match="Insufficient stock"):
        service.create_reservation(sku.id, 20, "idempotency-key-1")


def test_create_reservation_idempotency(service, repo):
    sku = service.create_sku("PROD-001", 100)
    reservation1 = service.create_reservation(sku.id, 10, "idempotency-key-1")
    reservation2 = service.create_reservation(sku.id, 10, "idempotency-key-1")
    assert reservation1.id == reservation2.id
    assert reservation1.order_id == reservation2.order_id

    # Stock should still be allocated once
    updated_sku = repo.get_sku_by_id(sku.id)
    assert updated_sku.reserved == 10


def test_create_reservation_after_expiration(service, repo):
    sku = service.create_sku("PROD-001", 100)
    reservation1 = service.create_reservation(sku.id, 10, "idempotency-key-1")
    original_order_id = reservation1.order_id

    # Expire the reservation manually for testing
    reservation1.expires_at = datetime.utcnow() - timedelta(seconds=1)
    repo.db.commit()

    # Retry with same idempotency key should create new reservation
    reservation2 = service.create_reservation(sku.id, 10, "idempotency-key-1")
    assert reservation2.id != reservation1.id
    assert reservation2.order_id != original_order_id
    assert reservation1.status == ReservationStatus.EXPIRED


def test_confirm_reservation_success(service, repo):
    sku = service.create_sku("PROD-001", 100)
    reservation = service.create_reservation(sku.id, 10, "idempotency-key-1")
    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == ReservationStatus.CONFIRMED
    assert confirmed.confirmed_at is not None


def test_confirm_expired_reservation_fails(service, repo):
    sku = service.create_sku("PROD-001", 100)
    reservation = service.create_reservation(sku.id, 10, "idempotency-key-1")
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    repo.db.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    # Expired reservation should release stock
    updated_sku = repo.get_sku_by_id(sku.id)
    assert updated_sku.reserved == 0


def test_cancel_reservation_success(service, repo):
    sku = service.create_sku("PROD-001", 100)
    reservation = service.create_reservation(sku.id, 10, "idempotency-key-1")
    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED

    # Stock should be released
    updated_sku = repo.get_sku_by_id(sku.id)
    assert updated_sku.reserved == 0


def test_cancel_confirmed_reservation_fails(service):
    sku = service.create_sku("PROD-001", 100)
    reservation = service.create_reservation(sku.id, 10, "idempotency-key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ServiceValidationError, match="immutable"):
        service.cancel_reservation(reservation.id)


def test_cleanup_expired_reservations(service, repo):
    sku = service.create_sku("PROD-001", 100)
    res1 = service.create_reservation(sku.id, 10, "idempotency-key-1")
    res2 = service.create_reservation(sku.id, 15, "idempotency-key-2")

    # Expire first reservation
    res1.expires_at = datetime.utcnow() - timedelta(seconds=1)
    repo.db.commit()

    count = service.cleanup_expired_reservations()
    assert count == 1

    # Stock should be released
    updated_sku = repo.get_sku_by_id(sku.id)
    assert updated_sku.reserved == 15  # Only res2's allocation remains


def test_list_orders(service, repo):
    sku = service.create_sku("PROD-001", 100)
    res1 = service.create_reservation(sku.id, 10, "key-1")
    res2 = service.create_reservation(sku.id, 15, "key-2")
    service.confirm_reservation(res1.id)
    service.confirm_reservation(res2.id)

    orders, total = service.list_orders(page=1, page_size=10)
    assert total == 2
    assert len(orders) == 2
