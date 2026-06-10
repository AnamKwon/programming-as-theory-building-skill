"""Tests for the service layer."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import Base, ReservationModel, SKUModel
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repository(db: Session) -> Repository:
    return Repository(db)


@pytest.fixture
def service(repository: Repository) -> CommerceService:
    return CommerceService(repository)


def test_create_sku(service: CommerceService):
    sku = service.create_sku("WIDGET-001", 100)
    assert sku.sku == "WIDGET-001"
    assert sku.available_stock == 100


def test_adjust_stock(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    result = service.adjust_stock("WIDGET-001", -20)
    assert result.available_stock == 80

    result = service.adjust_stock("WIDGET-001", 30)
    assert result.available_stock == 110


def test_adjust_stock_nonexistent(service: CommerceService):
    result = service.adjust_stock("NONEXISTENT", 10)
    assert result is None


def test_create_reservation_sufficient_stock(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    reservation, error = service.create_reservation("WIDGET-001", 30, "key-1")
    assert error is None
    assert reservation.id is not None
    assert reservation.quantity == 30
    assert reservation.status == "PENDING"

    sku = service.repo.get_sku_by_sku("WIDGET-001")
    assert sku.available_stock == 70


def test_create_reservation_insufficient_stock(service: CommerceService):
    service.create_sku("WIDGET-001", 50)
    reservation, error = service.create_reservation("WIDGET-001", 100, "key-1")
    assert error == "Insufficient stock"
    assert reservation is None

    sku = service.repo.get_sku_by_sku("WIDGET-001")
    assert sku.available_stock == 50


def test_create_reservation_idempotency(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    res1, err1 = service.create_reservation("WIDGET-001", 30, "key-1")
    assert err1 is None
    assert res1.id == 1

    sku = service.repo.get_sku_by_sku("WIDGET-001")
    stock_after_first = sku.available_stock

    res2, err2 = service.create_reservation("WIDGET-001", 30, "key-1")
    assert err2 is None
    assert res2.id == 1
    assert res2.quantity == 30

    sku = service.repo.get_sku_by_sku("WIDGET-001")
    assert sku.available_stock == stock_after_first


def test_confirm_reservation_success(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    reservation, _ = service.create_reservation("WIDGET-001", 30, "key-1")
    order, error = service.confirm_reservation(reservation.id)
    assert error is None
    assert order.id is not None
    assert order.sku == "WIDGET-001"
    assert order.quantity == 30

    res = service.repo.get_reservation_by_id(reservation.id)
    assert res.status == "CONFIRMED"


def test_confirm_reservation_nonexistent(service: CommerceService):
    order, error = service.confirm_reservation(999)
    assert error == "Reservation not found"
    assert order is None


def test_confirm_reservation_not_pending(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    reservation, _ = service.create_reservation("WIDGET-001", 30, "key-1")
    service.confirm_reservation(reservation.id)

    order, error = service.confirm_reservation(reservation.id)
    assert error == "Reservation is not in PENDING state"
    assert order is None


def test_confirm_reservation_expired(db: Session, service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    reservation, _ = service.create_reservation("WIDGET-001", 30, "key-1")

    past_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    res_model = db.query(ReservationModel).filter_by(id=reservation.id).first()
    res_model.created_at = past_time.replace(tzinfo=None)
    db.commit()

    order, error = service.confirm_reservation(reservation.id)
    assert error == "Reservation expired"
    assert order is None

    res = service.repo.get_reservation_by_id(reservation.id)
    assert res.status == "EXPIRED"

    sku = service.repo.get_sku_by_sku("WIDGET-001")
    assert sku.available_stock == 100


def test_cancel_reservation_success(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    reservation, _ = service.create_reservation("WIDGET-001", 30, "key-1")
    sku_before = service.repo.get_sku_by_sku("WIDGET-001")
    assert sku_before.available_stock == 70

    result, error = service.cancel_reservation(reservation.id)
    assert error is None
    assert result.status == "CANCELLED"

    sku_after = service.repo.get_sku_by_sku("WIDGET-001")
    assert sku_after.available_stock == 100


def test_cancel_reservation_not_pending(service: CommerceService):
    service.create_sku("WIDGET-001", 100)
    reservation, _ = service.create_reservation("WIDGET-001", 30, "key-1")
    service.confirm_reservation(reservation.id)

    result, error = service.cancel_reservation(reservation.id)
    assert error == "Reservation is not in PENDING state"
    assert result is None
