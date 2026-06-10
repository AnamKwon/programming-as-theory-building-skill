import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.commerce_service.models import Base, ReservationStatus, SKUStatus
from src.commerce_service.service import CommercService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(test_db):
    return CommercService(test_db)


def test_create_sku_success(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    assert sku.code == "TEST-SKU-001"
    assert sku.quantity_available == 100
    assert sku.status == SKUStatus.ACTIVE.value


def test_create_sku_duplicate_code(service):
    service.create_sku("TEST-SKU-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_sku("TEST-SKU-001", 50)
    assert exc_info.value.status_code == 409


def test_adjust_stock_success(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    adjusted = service.adjust_stock(sku.id, -10)
    assert adjusted.quantity_available == 90


def test_adjust_stock_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(999, 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")
    assert reservation.quantity == 50
    assert reservation.status == ReservationStatus.PENDING.value
    assert sku.id == reservation.sku_id


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(sku.id, 150, "idempotency-key-1")
    assert exc_info.value.status_code == 409
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_idempotent(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    res1 = service.create_reservation(sku.id, 50, "idempotency-key-1")
    res2 = service.create_reservation(sku.id, 50, "idempotency-key-1")
    assert res1.id == res2.id
    assert sku.quantity_available == 50  # Stock reserved once, not twice


def test_create_reservation_idempotent_cancelled(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    res1 = service.create_reservation(sku.id, 50, "idempotency-key-1")
    service.cancel_reservation(res1.id)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(sku.id, 50, "idempotency-key-1")
    assert exc_info.value.status_code == 409


def test_confirm_reservation_success(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")
    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == ReservationStatus.CONFIRMED.value


def test_confirm_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_confirm_reservation_expired(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    service.repo.session.commit()
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()


def test_cancel_reservation_success(service):
    sku = service.create_sku("TEST-SKU-001", 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")
    assert sku.quantity_available == 50
    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED.value
    sku = service.repo.get_sku(sku.id)
    assert sku.quantity_available == 100


def test_cancel_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404


def test_get_orders_pagination(service):
    sku = service.create_sku("TEST-SKU-001", 1000)
    for i in range(25):
        res = service.create_reservation(sku.id, 10, f"key-{i}")
        service.confirm_reservation(res.id)

    orders, total, page, page_size, has_more = service.get_orders(1, 10)
    assert len(orders) == 10
    assert total == 25
    assert page == 1
    assert page_size == 10
    assert has_more is True

    orders2, _, _, _, has_more2 = service.get_orders(3, 10)
    assert len(orders2) == 5
    assert has_more2 is False


def test_get_orders_invalid_page(service):
    with pytest.raises(HTTPException) as exc_info:
        service.get_orders(0, 10)
    assert exc_info.value.status_code == 400


def test_get_orders_invalid_page_size(service):
    with pytest.raises(HTTPException) as exc_info:
        service.get_orders(1, 101)
    assert exc_info.value.status_code == 400
