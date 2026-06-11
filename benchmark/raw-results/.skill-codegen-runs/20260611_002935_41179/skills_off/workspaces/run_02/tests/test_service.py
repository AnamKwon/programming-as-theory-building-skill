import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base, Reservation
from commerce_service.service import CommercService
from fastapi import HTTPException


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def test_create_sku(db_session):
    service = CommercService(db_session)
    sku = service.create_sku("SKU001", 100)
    assert sku.sku == "SKU001"
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_adjust_stock(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    sku = service.adjust_stock("SKU001", 50)
    assert sku.available_stock == 150


def test_adjust_stock_not_found(db_session):
    service = CommercService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    assert reservation.status == "PENDING"
    assert reservation.quantity == 30
    assert reservation.sku == "SKU001"


def test_create_reservation_insufficient_stock(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 20)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("SKU001", 50, "idempotency-1")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_idempotency(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    res1 = service.create_reservation("SKU001", 30, "idempotency-1")
    res2 = service.create_reservation("SKU001", 30, "idempotency-1")
    assert res1.id == res2.id
    assert res1.created_at == res2.created_at


def test_confirm_reservation_success(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == "CONFIRMED"


def test_confirm_reservation_expired(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")

    old_time = datetime.utcnow() - timedelta(seconds=301)
    db_session.query(Reservation).filter(Reservation.id == reservation.id).update(
        {"created_at": old_time}
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert "Reservation expired" in exc_info.value.detail


def test_confirm_reservation_not_pending(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.cancel_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert "not in PENDING status" in exc_info.value.detail


def test_cancel_reservation_success(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")

    sku_before = service.repo.get_sku_by_name("SKU001")
    assert sku_before.available_stock == 70
    assert sku_before.reserved_stock == 30

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "CANCELLED"

    sku_after = service.repo.get_sku_by_name("SKU001")
    assert sku_after.available_stock == 100
    assert sku_after.reserved_stock == 0


def test_cancel_reservation_not_pending(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_get_orders_pagination(db_session):
    service = CommercService(db_session)
    service.create_sku("SKU001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU001", 10, f"idempotency-{i}")
        service.confirm_reservation(res.id)

    orders_page1, total1 = service.get_orders(page=1, size=10)
    assert len(orders_page1) == 10
    assert total1 == 25

    orders_page2, total2 = service.get_orders(page=2, size=10)
    assert len(orders_page2) == 10
    assert total2 == 25

    orders_page3, total3 = service.get_orders(page=3, size=10)
    assert len(orders_page3) == 5
    assert total3 == 25
