import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def test_create_sku(db):
    """Test creating a new SKU."""
    service = CommerceService(db)
    sku = service.create_sku("SKU001", 100)
    assert sku.sku == "SKU001"
    assert sku.initial_stock == 100
    assert sku.available_stock == 100


def test_create_duplicate_sku(db):
    """Test that duplicate SKUs are rejected."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("SKU001", 50)


def test_adjust_stock(db):
    """Test adjusting stock levels."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    sku = service.adjust_stock("SKU001", 50)
    assert sku.available_stock == 150
    sku = service.adjust_stock("SKU001", -30)
    assert sku.available_stock == 120


def test_create_reservation_happy_path(db):
    """Test creating a reservation with sufficient stock."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-key-1")
    assert reservation.sku == "SKU001"
    assert reservation.quantity == 50
    assert reservation.status == ReservationStatus.PENDING
    assert reservation.idempotency_key == "idempotency-key-1"

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 50


def test_create_reservation_insufficient_stock(db):
    """Test that insufficient stock returns error."""
    service = CommerceService(db)
    service.create_sku("SKU001", 30)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 50, "idempotency-key-1")


def test_idempotent_reservation(db):
    """Test that idempotency key prevents duplicate reservations."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)

    first = service.create_reservation("SKU001", 50, "idempotency-key-1")
    second = service.create_reservation("SKU001", 50, "idempotency-key-1")

    assert first.id == second.id
    assert first.created_at == second.created_at

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 50


def test_confirm_reservation_happy_path(db):
    """Test confirming a reservation."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-key-1")

    order = service.confirm_reservation(reservation.id)
    assert order.reservation_id == reservation.id

    confirmed = service.repo.get_reservation(reservation.id)
    assert confirmed.status == ReservationStatus.CONFIRMED


def test_confirm_expired_reservation(db):
    """Test that expired reservations cannot be confirmed."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-key-1")

    from src.commerce_service.models import ReservationModel
    db_reservation = service.repo.get_reservation(reservation.id)
    db_reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
    db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)

    expired = service.repo.get_reservation(reservation.id)
    assert expired.status == ReservationStatus.EXPIRED

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 100


def test_confirm_non_pending_reservation(db):
    """Test that non-pending reservations cannot be confirmed."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-key-1")

    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="cannot be confirmed"):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(db):
    """Test canceling a reservation restores stock."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-key-1")

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 50

    service.cancel_reservation(reservation.id)

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku.available_stock == 100

    cancelled = service.repo.get_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED


def test_cancel_non_pending_reservation(db):
    """Test that non-pending reservations cannot be cancelled."""
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-key-1")

    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="cannot be cancelled"):
        service.cancel_reservation(reservation.id)


def test_get_orders_paginated(db):
    """Test paginated order retrieval."""
    service = CommerceService(db)
    service.create_sku("SKU001", 1000)

    for i in range(15):
        res = service.create_reservation("SKU001", 10, f"idempotency-key-{i}")
        service.confirm_reservation(res.id)

    orders, total = service.get_orders_paginated(1, 10)
    assert len(orders) == 10
    assert total == 15

    orders, total = service.get_orders_paginated(2, 10)
    assert len(orders) == 5
    assert total == 15
