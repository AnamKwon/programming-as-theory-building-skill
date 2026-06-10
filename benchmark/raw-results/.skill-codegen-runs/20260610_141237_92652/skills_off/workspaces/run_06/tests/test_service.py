"""Tests for the service layer."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.service import CommerceService


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
    return CommerceService(db)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku == "SKU-001"
    assert sku.initial_stock == 100
    assert sku.available_stock == 100


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    adjusted = service.adjust_stock("SKU-001", -10)
    assert adjusted.available_stock == 90


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    reservation, status_code = service.create_reservation("SKU-001", 50, "idempotent-1")
    assert status_code == 201
    assert reservation.sku == "SKU-001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    reservation, status_code = service.create_reservation("SKU-001", 50, "idempotent-1")
    assert status_code == 400
    assert reservation is None


def test_idempotent_reservation(service):
    service.create_sku("SKU-001", 100)
    res1, status1 = service.create_reservation("SKU-001", 50, "idempotent-1")
    res2, status2 = service.create_reservation("SKU-001", 50, "idempotent-1")
    assert status1 == 201
    assert status2 == 201
    assert res1.id == res2.id
    sku = service.sku_repo.get_sku_by_code("SKU-001")
    assert sku.available_stock == 50


def test_confirm_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "idempotent-1")
    order, status_code = service.confirm_reservation(reservation.id)
    assert status_code == 200
    assert order["reservation_id"] == reservation.id


def test_confirm_expired_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "idempotent-1")

    reservation.created_at = datetime.utcnow() - timedelta(seconds=310)
    service.reservation_repo.session.commit()

    order, status_code = service.confirm_reservation(reservation.id)
    assert status_code == 400
    assert order is None

    updated_res = service.reservation_repo.get_reservation_by_id(reservation.id)
    assert updated_res.status == "EXPIRED"

    sku = service.sku_repo.get_sku_by_code("SKU-001")
    assert sku.available_stock == 100


def test_cancel_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "idempotent-1")
    result, status_code = service.cancel_reservation(reservation.id)
    assert status_code == 200

    updated_res = service.reservation_repo.get_reservation_by_id(reservation.id)
    assert updated_res.status == "CANCELLED"

    sku = service.sku_repo.get_sku_by_code("SKU-001")
    assert sku.available_stock == 100


def test_cancel_non_pending_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "idempotent-1")
    service.confirm_reservation(reservation.id)

    result, status_code = service.cancel_reservation(reservation.id)
    assert status_code == 400


def test_pagination(service):
    for i in range(25):
        service.create_sku(f"SKU-{i}", 100)
        reservation, _ = service.create_reservation(f"SKU-{i}", 10, f"idempotent-{i}")
        service.confirm_reservation(reservation.id)

    orders1, total1 = service.get_orders_paginated(1, 10)
    orders2, total2 = service.get_orders_paginated(2, 10)
    orders3, total3 = service.get_orders_paginated(3, 10)

    assert len(orders1) == 10
    assert len(orders2) == 10
    assert len(orders3) == 5
    assert total1 == 25
    assert total2 == 25
    assert total3 == 25
