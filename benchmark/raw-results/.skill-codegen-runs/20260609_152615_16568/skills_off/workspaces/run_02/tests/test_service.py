import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    repo = Repository(db)
    return CommerceService(repo, reservation_ttl_minutes=30)


def test_create_sku(service):
    sku = service.create_sku("SKU001", "Widget", 9.99)
    assert sku.id == "SKU001"
    assert sku.name == "Widget"
    assert sku.price == 9.99


def test_create_sku_idempotent(service):
    sku1 = service.create_sku("SKU001", "Widget", 9.99)
    sku2 = service.create_sku("SKU001", "Widget", 9.99)
    assert sku1.id == sku2.id


def test_adjust_stock(service):
    service.create_sku("SKU001", "Widget", 9.99)
    inventory = service.adjust_stock("SKU001", 100)
    assert inventory.available == 100
    assert inventory.reserved == 0


def test_insufficient_stock_error(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 10)

    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 20)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    assert reservation.id is not None
    assert reservation.sku_id == "SKU001"
    assert reservation.quantity == 10
    assert reservation.status == ReservationStatus.PENDING

    inventory = service.get_inventory("SKU001")
    assert inventory.available == 90
    assert inventory.reserved == 10


def test_reservation_idempotency(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    key = "idempotency-key-123"
    res1 = service.create_reservation("SKU001", 10, idempotency_key=key)
    res2 = service.create_reservation("SKU001", 10, idempotency_key=key)

    assert res1.id == res2.id

    inventory = service.get_inventory("SKU001")
    assert inventory.available == 90
    assert inventory.reserved == 10


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    confirmed = service.confirm_reservation(reservation.id)

    assert confirmed.status == ReservationStatus.CONFIRMED
    assert confirmed.confirmed_at is not None

    inventory = service.get_inventory("SKU001")
    assert inventory.available == 90
    assert inventory.reserved == 0


def test_cancel_pending_reservation(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == ReservationStatus.CANCELLED

    inventory = service.get_inventory("SKU001")
    assert inventory.available == 100
    assert inventory.reserved == 0


def test_cancel_confirmed_reservation(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    service.confirm_reservation(reservation.id)
    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == ReservationStatus.CANCELLED


def test_reservation_expiration(service, db):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    # Create reservation
    repo = Repository(db)
    reservation_id = "test-123"
    expires_at = datetime.utcnow() - timedelta(minutes=1)  # Expired
    repo.create_reservation(reservation_id, "SKU001", 10, expires_at)
    db.commit()

    # Try to get expired reservation
    with pytest.raises(ReservationExpiredError):
        service.get_reservation(reservation_id)

    # Inventory should be released
    inventory = service.get_inventory("SKU001")
    assert inventory.reserved == 0
    assert inventory.available == 100


def test_list_orders(service):
    service.create_sku("SKU001", "Widget", 9.99)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    service.confirm_reservation(reservation.id)

    orders, total = service.list_orders(skip=0, limit=20)
    assert total == 1
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.CONFIRMED
