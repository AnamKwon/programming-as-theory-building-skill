import pytest
import tempfile
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.service import CommerceService
from src.commerce_service.repository import SKURepository, ReservationRepository


@pytest.fixture
def temp_db():
    db_fd, db_path = tempfile.mkstemp()
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    os.close(db_fd)
    os.unlink(db_path)


def test_create_sku(temp_db):
    service = CommerceService(temp_db)
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100


def test_adjust_stock(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -30)
    assert result.available_stock == 70


def test_create_reservation_success(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)

    reservation, status_code = service.create_reservation("SKU001", 50, "key001")
    assert status_code == 201
    assert reservation.sku == "SKU001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"


def test_insufficient_stock(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 30)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 50, "key001")


def test_idempotent_reservation(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)

    reservation1, status1 = service.create_reservation("SKU001", 50, "key001")

    # Second call with same idempotency key should return 200 and not deduct stock again
    reservation2, status2 = service.create_reservation("SKU001", 50, "key001")

    assert status2 == 200
    assert reservation1.id == reservation2.id

    # Stock should only be deducted once
    stock = service.sku_repo.get_available_stock("SKU001")
    assert stock == 50


def test_confirm_reservation(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key001")

    order = service.confirm_reservation(reservation.id)
    assert order.sku == "SKU001"
    assert order.quantity == 50
    assert order.reservation_id == reservation.id


def test_expired_reservation(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key001")

    # Manually set created_at to 301 seconds ago
    res_record = service.reservation_repo.get_reservation(reservation.id)
    res_record.created_at = datetime.utcnow() - timedelta(seconds=301)
    temp_db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)

    # Check status changed to EXPIRED
    updated = service.reservation_repo.get_reservation(reservation.id)
    assert updated.status == "EXPIRED"

    # Check stock was restored
    stock = service.sku_repo.get_available_stock("SKU001")
    assert stock == 100


def test_cancel_reservation(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key001")

    result = service.cancel_reservation(reservation.id)
    assert result.status == "CANCELLED"

    # Check stock was restored
    stock = service.sku_repo.get_available_stock("SKU001")
    assert stock == 100


def test_confirm_non_pending_reservation(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "key001")

    # Cancel it first
    service.cancel_reservation(reservation.id)

    # Try to confirm cancelled reservation
    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(reservation.id)


def test_get_orders(temp_db):
    service = CommerceService(temp_db)
    service.create_sku("SKU001", 100)

    for i in range(15):
        reservation, _ = service.create_reservation("SKU001", 1, f"key{i}")
        service.confirm_reservation(reservation.id)

    orders, total = service.get_orders(1, 10)
    assert len(orders) == 10
    assert total == 15

    orders_page2, total = service.get_orders(2, 10)
    assert len(orders_page2) == 5
    assert total == 15
