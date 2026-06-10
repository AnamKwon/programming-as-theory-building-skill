import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.service import CommerceService


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
    return CommerceService(db)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", "Test Product", 100)
    assert sku.sku_code == "SKU-001"
    assert sku.name == "Test Product"
    assert sku.stock_quantity == 100


def test_create_duplicate_sku_fails(service):
    service.create_sku("SKU-001", "Product 1", 50)
    with pytest.raises(Exception):
        service.create_sku("SKU-001", "Product 2", 30)


def test_adjust_stock(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    adjusted = service.adjust_stock(sku.id, 50)
    assert adjusted.stock_quantity == 150


def test_adjust_stock_negative(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    with pytest.raises(Exception):
        service.adjust_stock(sku.id, -150)


def test_create_reservation_success(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    reservation = service.create_reservation(sku.id, 30)
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 30
    assert reservation.status == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    with pytest.raises(Exception) as exc_info:
        service.create_reservation(sku.id, 150)
    assert "Insufficient stock" in str(exc_info.value.detail)


def test_create_reservation_with_idempotency_key(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    res1 = service.create_reservation(sku.id, 30, "key-123")
    res2 = service.create_reservation(sku.id, 30, "key-123")
    assert res1.id == res2.id


def test_create_reservation_expired_idempotency_key(service, db):
    sku = service.create_sku("SKU-001", "Product", 100)
    res = service.create_reservation(sku.id, 30, "key-123")

    # Mark reservation as expired in DB
    from src.commerce_service.models import Reservation
    db_res = db.query(Reservation).filter(Reservation.id == res.id).first()
    db_res.status = ReservationStatus.EXPIRED
    db.commit()

    with pytest.raises(Exception) as exc_info:
        service.create_reservation(sku.id, 30, "key-123")
    assert "expired" in str(exc_info.value.detail).lower()


def test_confirm_reservation(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    reservation = service.create_reservation(sku.id, 30)
    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == ReservationStatus.CONFIRMED


def test_confirm_non_pending_reservation_fails(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    reservation = service.create_reservation(sku.id, 30)
    service.confirm_reservation(reservation.id)
    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation.id)
    assert "Cannot confirm" in str(exc_info.value.detail)


def test_cancel_reservation(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    reservation = service.create_reservation(sku.id, 30)
    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED


def test_cancel_non_pending_reservation_fails(service):
    sku = service.create_sku("SKU-001", "Product", 100)
    reservation = service.create_reservation(sku.id, 30)
    service.cancel_reservation(reservation.id)
    with pytest.raises(Exception) as exc_info:
        service.cancel_reservation(reservation.id)
    assert "Cannot cancel" in str(exc_info.value.detail)


def test_reservation_ttl_expiration(service, db):
    sku = service.create_sku("SKU-001", "Product", 100)
    reservation = service.create_reservation(sku.id, 30)

    from src.commerce_service.models import Reservation
    db_res = db.query(Reservation).filter(Reservation.id == reservation.id).first()
    db_res.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation.id)
    assert "expired" in str(exc_info.value.detail).lower()


def test_pagination_valid(service):
    for i in range(25):
        service.order_repo.create()

    orders, total, page, page_size, total_pages = service.get_orders_paginated(1, 10)
    assert len(orders) == 10
    assert total == 25
    assert total_pages == 3


def test_pagination_invalid_page(service):
    with pytest.raises(Exception) as exc_info:
        service.get_orders_paginated(0, 10)
    assert "Page must be >= 1" in str(exc_info.value.detail)


def test_pagination_invalid_page_size(service):
    with pytest.raises(Exception) as exc_info:
        service.get_orders_paginated(1, 200)
    assert "Page size must be between 1 and 100" in str(exc_info.value.detail)
