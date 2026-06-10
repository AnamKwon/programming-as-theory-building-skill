import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, SKUModel, ReservationModel, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
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
def repo(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repo):
    return Service(repo)


def test_create_sku(service):
    sku = service.create_sku("SKU001", "Product 1", "A test product", 100)
    assert sku.code == "SKU001"
    assert sku.name == "Product 1"
    assert sku.stock_quantity == 100


def test_adjust_stock(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    sku = service.adjust_stock(sku.id, 50)
    assert sku.stock_quantity == 150

    sku = service.adjust_stock(sku.id, -30)
    assert sku.stock_quantity == 120


def test_adjust_stock_not_found(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock(999, 10)


def test_create_reservation_success(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    reservation = service.create_reservation(sku.id, 50)
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 50
    assert reservation.status == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 150)


def test_create_reservation_accounts_for_pending(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    service.create_reservation(sku.id, 80)
    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 30)


def test_create_reservation_idempotency(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    key = "idempotency-key-123"
    res1 = service.create_reservation(sku.id, 50, key)
    res2 = service.create_reservation(sku.id, 50, key)
    assert res1.id == res2.id


def test_confirm_reservation_success(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    reservation = service.create_reservation(sku.id, 50)
    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == ReservationStatus.CONFIRMED


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_confirm_reservation_expired(service, db_session):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    repo = Repository(db_session)
    expired_at = datetime.utcnow() - timedelta(minutes=1)
    reservation = repo.create_reservation(sku.id, 50, expired_at)
    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_already_confirmed(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    reservation = service.create_reservation(sku.id, 50)
    service.confirm_reservation(reservation.id)
    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    reservation = service.create_reservation(sku.id, 50)
    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(999)


def test_cancel_reservation_idempotent(service):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    reservation = service.create_reservation(sku.id, 50)
    service.cancel_reservation(reservation.id)
    result = service.cancel_reservation(reservation.id)
    assert result.status == ReservationStatus.CANCELLED


def test_cleanup_expired_reservations(service, db_session):
    sku = service.create_sku("SKU001", "Product 1", None, 100)
    repo = Repository(db_session)
    expired_at = datetime.utcnow() - timedelta(minutes=1)
    repo.create_reservation(sku.id, 50, expired_at)
    repo.create_reservation(sku.id, 20, datetime.utcnow() + timedelta(minutes=30))

    count = service.cleanup_expired_reservations()
    assert count == 1
