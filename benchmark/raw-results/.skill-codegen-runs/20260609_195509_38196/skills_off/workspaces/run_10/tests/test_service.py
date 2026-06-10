import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
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
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    assert sku.code == "SKU001"
    assert sku.price == Decimal("19.99")
    assert sku.stock_quantity == 100


def test_create_duplicate_sku_fails(service):
    service.create_sku("SKU001", Decimal("19.99"), 100)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("SKU001", Decimal("29.99"), 50)


def test_adjust_stock(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    updated = service.adjust_stock(sku.id, 10)
    assert updated.stock_quantity == 110

    updated = service.adjust_stock(sku.id, -20)
    assert updated.stock_quantity == 90


def test_adjust_stock_negative_fails(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 10)
    with pytest.raises(ValueError, match="cannot be negative"):
        service.adjust_stock(sku.id, -20)


def test_create_reservation_happy_path(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        ttl_seconds=3600,
    )
    assert reservation.quantity == 10
    assert reservation.status == "pending"
    assert reservation.sku_id == sku.id

    updated_sku = service.skus.get_by_id(sku.id)
    assert updated_sku.stock_quantity == 90


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation(
            sku_id=sku.id,
            quantity=20,
            customer_id="customer1",
            ttl_seconds=3600,
        )


def test_create_reservation_idempotent(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    res1 = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        ttl_seconds=3600,
        idempotency_key="idem-key-1",
    )

    res2 = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        ttl_seconds=3600,
        idempotency_key="idem-key-1",
    )

    assert res1.id == res2.id
    updated_sku = service.skus.get_by_id(sku.id)
    assert updated_sku.stock_quantity == 90


def test_idempotency_key_reused_after_confirmation_fails(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    res1 = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        ttl_seconds=3600,
        idempotency_key="idem-key-1",
    )
    service.confirm_reservation(res1.id)

    with pytest.raises(ValueError, match="already processed"):
        service.create_reservation(
            sku_id=sku.id,
            quantity=5,
            customer_id="customer1",
            ttl_seconds=3600,
            idempotency_key="idem-key-1",
        )


def test_confirm_reservation(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        ttl_seconds=3600,
    )

    order = service.confirm_reservation(reservation.id)
    assert order.sku_id == sku.id
    assert order.quantity == 10
    assert order.customer_id == "customer1"

    updated_reservation = service.reservations.get_by_id(reservation.id)
    assert updated_reservation.status == "confirmed"


def test_confirm_expired_reservation(service, db):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    expires_at = datetime.utcnow() - timedelta(seconds=1)
    reservation = service.reservations.create(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        expires_at=expires_at,
    )
    service.skus.update_stock(sku.id, -10)

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)

    updated_reservation = service.reservations.get_by_id(reservation.id)
    assert updated_reservation.status == "expired"

    updated_sku = service.skus.get_by_id(sku.id)
    assert updated_sku.stock_quantity == 100


def test_cancel_reservation(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 100)
    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        customer_id="customer1",
        ttl_seconds=3600,
    )

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "cancelled"

    updated_sku = service.skus.get_by_id(sku.id)
    assert updated_sku.stock_quantity == 100


def test_list_orders_paginated(service):
    sku = service.create_sku("SKU001", Decimal("19.99"), 1000)

    for i in range(25):
        res = service.create_reservation(
            sku_id=sku.id,
            quantity=1,
            customer_id=f"customer{i}",
            ttl_seconds=3600,
        )
        service.confirm_reservation(res.id)

    items, total = service.list_orders(offset=0, limit=10)
    assert len(items) == 10
    assert total == 25

    items, total = service.list_orders(offset=10, limit=10)
    assert len(items) == 10

    items, total = service.list_orders(offset=20, limit=10)
    assert len(items) == 5
