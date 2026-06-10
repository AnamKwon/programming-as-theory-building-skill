"""Tests for service layer."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    IdempotencyViolationError,
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(test_db):
    return CommerceService(test_db)


def test_create_sku(service):
    sku = service.create_sku("WIDGET-001", 100.0)
    assert sku.id is not None
    assert sku.name == "WIDGET-001"
    assert sku.quantity_available == 100.0


def test_adjust_stock(service):
    sku = service.create_sku("GADGET-001", 50.0)
    updated = service.adjust_stock(sku.id, 25.0)
    assert updated.quantity_available == 75.0

    updated = service.adjust_stock(sku.id, -30.0)
    assert updated.quantity_available == 45.0


def test_reserve_inventory_sufficient_stock(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    reservation = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)

    assert reservation.id is not None
    assert reservation.status == "pending"
    assert reservation.quantity == 30.0
    assert reservation.sku_id == sku.id


def test_reserve_inventory_insufficient_stock(service):
    sku = service.create_sku("PRODUCT-001", 50.0)

    with pytest.raises(InsufficientStockError):
        service.reserve_inventory(sku.id, 100.0, "idempotency-key-1", 300)


def test_reserve_inventory_idempotency(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    res1 = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)
    res2 = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)

    assert res1.id == res2.id
    assert res1.status == res2.status


def test_confirm_reservation(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    reservation = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)

    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == "confirmed"

    updated_sku = service.sku_repo.get_by_id(sku.id)
    assert updated_sku.quantity_available == 70.0


def test_confirm_expired_reservation(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    reservation = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 1)

    import time
    time.sleep(2)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_cancel_pending_reservation(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    reservation = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "cancelled"


def test_cancel_confirmed_reservation(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    reservation = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)
    service.confirm_reservation(reservation.id)

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "cancelled"

    updated_sku = service.sku_repo.get_by_id(sku.id)
    assert updated_sku.quantity_available == 100.0


def test_concurrent_reservations_reduce_available_stock(service):
    sku = service.create_sku("PRODUCT-001", 100.0)

    res1 = service.reserve_inventory(sku.id, 40.0, "idempotency-key-1", 300)
    res2 = service.reserve_inventory(sku.id, 40.0, "idempotency-key-2", 300)

    with pytest.raises(InsufficientStockError):
        service.reserve_inventory(sku.id, 30.0, "idempotency-key-3", 300)


def test_invalid_state_transition(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    reservation = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)

    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(reservation.id)


def test_idempotency_cancelled_reservation(service):
    sku = service.create_sku("PRODUCT-001", 100.0)
    res1 = service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)
    service.cancel_reservation(res1.id)

    with pytest.raises(IdempotencyViolationError):
        service.reserve_inventory(sku.id, 30.0, "idempotency-key-1", 300)
