"""Tests for service layer business logic."""

import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.service import ConflictError, NotFoundError, Service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    return Service(db)


def test_create_sku(service):
    sku = service.create_sku("SKU001", "Test Product", 100)
    assert sku.id == "SKU001"
    assert sku.name == "Test Product"
    assert sku.stock == 100


def test_create_duplicate_sku(service):
    service.create_sku("SKU001", "Test Product", 100)
    with pytest.raises(ConflictError):
        service.create_sku("SKU001", "Another", 50)


def test_adjust_stock(service):
    service.create_sku("SKU001", "Test Product", 100)
    updated = service.adjust_stock("SKU001", 10)
    assert updated.stock == 110

    updated = service.adjust_stock("SKU001", -30)
    assert updated.stock == 80


def test_adjust_stock_nonexistent(service):
    with pytest.raises(NotFoundError):
        service.adjust_stock("NONEXISTENT", 10)


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", "Test Product", 50)
    with pytest.raises(ConflictError):
        service.adjust_stock("SKU001", -60)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    assert reservation.sku_id == "SKU001"
    assert reservation.quantity == 30
    assert reservation.status == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Test Product", 50)
    with pytest.raises(ConflictError) as exc:
        service.create_reservation("SKU001", 60, "idempotency-1")
    assert "Insufficient stock" in str(exc.value)


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", "Test Product", 100)
    res1 = service.create_reservation("SKU001", 30, "idempotency-1")
    res2 = service.create_reservation("SKU001", 30, "idempotency-1")
    assert res1.id == res2.id


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(NotFoundError):
        service.create_reservation("NONEXISTENT", 10, "idempotency-1")


def test_create_reservation_reserved_stock_counts(service):
    service.create_sku("SKU001", "Test Product", 100)
    service.create_reservation("SKU001", 40, "res-1")
    service.create_reservation("SKU001", 50, "res-2")

    with pytest.raises(ConflictError):
        service.create_reservation("SKU001", 20, "res-3")


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")

    order = service.confirm_reservation(reservation.id)
    assert order.sku_id == "SKU001"
    assert order.quantity == 30

    updated_sku = service.repo.get_sku("SKU001")
    assert updated_sku.stock == 70

    updated_reservation = service.repo.get_reservation(reservation.id)
    assert updated_reservation.status == ReservationStatus.CONFIRMED


def test_confirm_nonexistent_reservation(service):
    with pytest.raises(NotFoundError):
        service.confirm_reservation("NONEXISTENT")


def test_confirm_already_confirmed_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ConflictError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == ReservationStatus.CANCELLED


def test_cancel_nonexistent_reservation(service):
    with pytest.raises(NotFoundError):
        service.cancel_reservation("NONEXISTENT")


def test_cancel_confirmed_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ConflictError):
        service.cancel_reservation(reservation.id)


def test_reservation_expiration(service):
    service.create_sku("SKU001", "Test Product", 100)

    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.repo.session.query(Base).filter(Base.id == reservation.id).update(
        {"expires_at": datetime.utcnow() - timedelta(seconds=1)}
    )
    service.repo.session.commit()

    with pytest.raises(ConflictError) as exc:
        service.confirm_reservation(reservation.id)
    assert "expired" in str(exc.value)

    updated_reservation = service.repo.get_reservation(reservation.id)
    assert updated_reservation.status == ReservationStatus.EXPIRED


def test_get_orders_pagination(service):
    service.create_sku("SKU001", "Product 1", 100)
    service.create_sku("SKU002", "Product 2", 100)

    for i in range(5):
        res = service.create_reservation("SKU001", 10, f"idempotency-{i}")
        service.confirm_reservation(res.id)

    orders, total = service.get_orders(page=1, page_size=2)
    assert len(orders) == 2
    assert total == 5

    orders, total = service.get_orders(page=2, page_size=2)
    assert len(orders) == 2

    orders, total = service.get_orders(page=3, page_size=2)
    assert len(orders) == 1
