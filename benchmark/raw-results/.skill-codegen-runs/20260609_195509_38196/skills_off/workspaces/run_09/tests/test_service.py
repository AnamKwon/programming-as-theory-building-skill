import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommercService,
    ReservationExpired,
    ReservationNotFound,
    SKUNotFound,
    StockUnavailable,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    return CommercService(repo)


def test_create_sku(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    assert sku.sku_code == "SKU001"
    assert sku.current_stock == 100
    assert sku.reserved_count == 0


def test_create_duplicate_sku_raises(service):
    service.create_sku("SKU001", initial_stock=100)
    with pytest.raises(ValueError):
        service.create_sku("SKU001", initial_stock=50)


def test_adjust_stock_positive(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    adjusted = service.adjust_stock(sku.id, 50)
    assert adjusted.current_stock == 150


def test_adjust_stock_negative(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    adjusted = service.adjust_stock(sku.id, -30)
    assert adjusted.current_stock == 70


def test_adjust_stock_negative_raises(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    with pytest.raises(ValueError):
        service.adjust_stock(sku.id, -150)


def test_adjust_stock_nonexistent_sku_raises(service):
    with pytest.raises(SKUNotFound):
        service.adjust_stock(999, 10)


def test_reserve_inventory_success(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    reservation = service.reserve_inventory(sku.id, 30, "idem-key-1", ttl_seconds=300)

    assert reservation.status == ReservationStatus.PENDING
    assert reservation.quantity == 30
    assert reservation.idempotency_key == "idem-key-1"

    # Check stock was reserved
    sku = service.repo.get_sku(sku.id)
    assert sku.current_stock == 100  # Not deducted yet
    assert sku.reserved_count == 30


def test_reserve_inventory_insufficient_stock(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    with pytest.raises(StockUnavailable):
        service.reserve_inventory(sku.id, 150, "idem-key-1")


def test_reserve_inventory_idempotency(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    res1 = service.reserve_inventory(sku.id, 30, "idem-key-1", ttl_seconds=300)
    res2 = service.reserve_inventory(sku.id, 30, "idem-key-1", ttl_seconds=300)

    assert res1.id == res2.id


def test_reserve_inventory_nonexistent_sku_raises(service):
    with pytest.raises(SKUNotFound):
        service.reserve_inventory(999, 30, "idem-key-1")


def test_confirm_reservation_success(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    reservation = service.reserve_inventory(sku.id, 30, "idem-key-1", ttl_seconds=300)

    confirmed_res, order = service.confirm_reservation(reservation.id)

    assert confirmed_res.status == ReservationStatus.CONFIRMED
    assert order.quantity == 30

    # Check stock was deducted
    sku = service.repo.get_sku(sku.id)
    assert sku.current_stock == 70  # Deducted
    assert sku.reserved_count == 0


def test_confirm_reservation_nonexistent_raises(service):
    with pytest.raises(ReservationNotFound):
        service.confirm_reservation(999)


def test_confirm_reservation_expired_raises(service, repo):
    sku = service.create_sku("SKU001", initial_stock=100)

    # Create an expired reservation manually
    from src.commerce_service.models import ReservationModel
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    res = repo.create_reservation(sku.id, 30, "idem-key-1", expired_at)

    # Reserve stock manually
    repo.update_sku_stock(sku.id, 100, 30)

    with pytest.raises(ReservationExpired):
        service.confirm_reservation(res.id)


def test_cancel_reservation_success(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    reservation = service.reserve_inventory(sku.id, 30, "idem-key-1", ttl_seconds=300)

    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == ReservationStatus.CANCELLED

    # Check stock was released
    sku = service.repo.get_sku(sku.id)
    assert sku.current_stock == 100
    assert sku.reserved_count == 0


def test_cancel_reservation_nonexistent_raises(service):
    with pytest.raises(ReservationNotFound):
        service.cancel_reservation(999)


def test_cancel_confirmed_reservation_raises(service):
    sku = service.create_sku("SKU001", initial_stock=100)
    reservation = service.reserve_inventory(sku.id, 30, "idem-key-1", ttl_seconds=300)
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError):
        service.cancel_reservation(reservation.id)


def test_list_orders_pagination(service):
    sku = service.create_sku("SKU001", initial_stock=1000)

    # Create and confirm 5 orders
    for i in range(5):
        res = service.reserve_inventory(sku.id, 10, f"idem-{i}", ttl_seconds=300)
        service.confirm_reservation(res.id)

    # Test pagination
    orders, total = service.list_orders(skip=0, limit=2)
    assert len(orders) == 2
    assert total == 5

    orders, total = service.list_orders(skip=2, limit=2)
    assert len(orders) == 2

    orders, total = service.list_orders(skip=4, limit=2)
    assert len(orders) == 1
