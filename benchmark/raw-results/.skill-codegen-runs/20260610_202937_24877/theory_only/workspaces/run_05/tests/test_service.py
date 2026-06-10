import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from src.commerce_service.models import Base, SKU, Reservation, Order
from src.commerce_service.service import CommerceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def test_create_sku(db):
    service = CommerceService(db)
    sku = service.create_sku("SKU001", 100)
    assert sku.sku == "SKU001"
    assert sku.available_stock == 100


def test_adjust_stock(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -10)
    assert result.available_stock == 90


def test_create_reservation_success(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "idem-key-1")
    assert reservation.status == "PENDING"
    assert reservation.quantity == 10

    sku = db.query(SKU).filter(SKU.sku == "SKU001").first()
    assert sku.available_stock == 90


def test_create_reservation_insufficient_stock(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 5)

    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU001", 10, "idem-key-1")
    assert exc.value.status_code == 400
    assert "Insufficient stock" in str(exc.value.detail)


def test_reservation_idempotency(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 100)

    res1 = service.create_reservation("SKU001", 10, "idem-key-1")
    res2 = service.create_reservation("SKU001", 10, "idem-key-1")

    assert res1.id == res2.id

    sku = db.query(SKU).filter(SKU.sku == "SKU001").first()
    assert sku.available_stock == 90


def test_confirm_reservation_success(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")

    confirmed = service.confirm_reservation(res.id)
    assert confirmed.status == "CONFIRMED"

    order = db.query(Order).filter(Order.reservation_id == res.id).first()
    assert order is not None
    assert order.quantity == 10


def test_confirm_reservation_expired(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")

    db.query(Reservation).filter(Reservation.id == res.id).update(
        {"created_at": datetime.utcnow() - timedelta(seconds=301)}
    )
    db.commit()

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(res.id)
    assert exc.value.status_code == 400
    assert "Reservation expired" in str(exc.value.detail)

    updated_res = db.query(Reservation).filter(Reservation.id == res.id).first()
    assert updated_res.status == "EXPIRED"

    sku = db.query(SKU).filter(SKU.sku == "SKU001").first()
    assert sku.available_stock == 100


def test_cancel_reservation_success(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")

    cancelled = service.cancel_reservation(res.id)
    assert cancelled.status == "CANCELLED"

    sku = db.query(SKU).filter(SKU.sku == "SKU001").first()
    assert sku.available_stock == 100


def test_get_orders_pagination(db):
    service = CommerceService(db)
    service.create_sku("SKU001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU001", 10, f"idem-key-{i}")
        service.confirm_reservation(res.id)

    orders1, total1 = service.get_orders(page=1, size=10)
    assert len(orders1) == 10
    assert total1 == 25

    orders2, total2 = service.get_orders(page=2, size=10)
    assert len(orders2) == 10
    assert total2 == 25

    orders3, total3 = service.get_orders(page=3, size=10)
    assert len(orders3) == 5
    assert total3 == 25
