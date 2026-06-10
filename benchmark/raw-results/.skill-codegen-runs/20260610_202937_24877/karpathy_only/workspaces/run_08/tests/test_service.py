import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.repository import Base, Repository, SKU, Reservation
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    yield SessionLocal()
    os.unlink(db_path)


@pytest.fixture
def service(temp_db):
    repo = Repository(temp_db)
    return CommerceService(repo)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku == "SKU-001"
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    adjusted = service.adjust_stock("SKU-001", 50)
    assert adjusted.available_stock == 150

    adjusted = service.adjust_stock("SKU-001", -30)
    assert adjusted.available_stock == 120


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idem-1")
    assert reservation.sku == "SKU-001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idem-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 50, "idem-1")


def test_create_reservation_idempotent(service):
    service.create_sku("SKU-001", 100)
    res1 = service.create_reservation("SKU-001", 50, "idem-1")
    res2 = service.create_reservation("SKU-001", 50, "idem-1")
    assert res1.id == res2.id
    assert res1.idempotency_key == res2.idempotency_key

    sku_record = service.repo.get_sku_by_sku("SKU-001")
    assert sku_record.available_stock == 50
    assert sku_record.reserved_stock == 50


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idem-1")
    confirmed_res, order = service.confirm_reservation(reservation.id)
    assert confirmed_res.status == "CONFIRMED"
    assert order.reservation_id == reservation.id

    sku_record = service.repo.get_sku_by_sku("SKU-001")
    assert sku_record.available_stock == 50
    assert sku_record.reserved_stock == 0


def test_confirm_reservation_expired(service, temp_db):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idem-1")

    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = old_time
    temp_db.commit()

    with pytest.raises(ValueError, match="Reservation expired"):
        service.confirm_reservation(reservation.id)

    sku_record = service.repo.get_sku_by_sku("SKU-001")
    assert sku_record.available_stock == 100
    assert sku_record.reserved_stock == 0

    expired_res = service.repo.get_reservation_by_id(reservation.id)
    assert expired_res.status == "EXPIRED"


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idem-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idem-1")

    sku_before = service.repo.get_sku_by_sku("SKU-001")
    assert sku_before.available_stock == 50
    assert sku_before.reserved_stock == 50

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "CANCELLED"

    sku_after = service.repo.get_sku_by_sku("SKU-001")
    assert sku_after.available_stock == 100
    assert sku_after.reserved_stock == 0


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idem-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.cancel_reservation(reservation.id)
