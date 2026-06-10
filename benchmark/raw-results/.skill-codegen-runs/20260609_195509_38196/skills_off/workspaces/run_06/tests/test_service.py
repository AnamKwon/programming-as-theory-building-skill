import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import DB_PATH, init_db
from commerce_service.service import (
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)


@pytest.fixture(autouse=True)
def setup_db():
    if DB_PATH.exists():
        os.remove(DB_PATH)
    init_db()
    yield
    if DB_PATH.exists():
        os.remove(DB_PATH)


def test_create_sku():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    assert sku["code"] == "SKU-001"
    assert sku["name"] == "Widget"
    assert sku["current_stock"] == 100


def test_adjust_stock_increase():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    updated = Service.adjust_stock(sku["id"], 50)
    assert updated["current_stock"] == 150


def test_adjust_stock_decrease():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    updated = Service.adjust_stock(sku["id"], -30)
    assert updated["current_stock"] == 70


def test_adjust_stock_insufficient():
    sku = Service.create_sku("SKU-001", "Widget", 10)
    with pytest.raises(InsufficientStockError):
        Service.adjust_stock(sku["id"], -20)


def test_adjust_stock_sku_not_found():
    with pytest.raises(SKUNotFoundError):
        Service.adjust_stock(999, 10)


def test_create_reservation_success():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    reservation = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    assert reservation["sku_id"] == sku["id"]
    assert reservation["quantity"] == 10
    assert reservation["status"] == ReservationStatus.PENDING.value
    assert reservation["idempotency_key"] == "idempotency-1"


def test_create_reservation_idempotent():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    res1 = Service.create_reservation(sku["id"], 10, "idempotency-1", ttl_seconds=3600)
    res2 = Service.create_reservation(sku["id"], 10, "idempotency-1", ttl_seconds=3600)
    assert res1["id"] == res2["id"]


def test_create_reservation_insufficient_stock():
    sku = Service.create_sku("SKU-001", "Widget", 10)
    with pytest.raises(InsufficientStockError):
        Service.create_reservation(sku["id"], 20, "idempotency-1", ttl_seconds=3600)


def test_create_reservation_sku_not_found():
    with pytest.raises(SKUNotFoundError):
        Service.create_reservation(999, 10, "idempotency-1", ttl_seconds=3600)


def test_confirm_reservation_success():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    reservation = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    confirmed_res, order_id = Service.confirm_reservation(reservation["id"])

    assert confirmed_res["status"] == ReservationStatus.CONFIRMED.value
    assert confirmed_res["confirmed_at"] is not None
    assert order_id is not None

    updated_sku = Service.get_order(order_id)
    assert updated_sku is not None


def test_confirm_reservation_insufficient_stock_at_confirm():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    reservation = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )

    Service.adjust_stock(sku["id"], -95)

    with pytest.raises(InsufficientStockError):
        Service.confirm_reservation(reservation["id"])


def test_confirm_reservation_expired():
    import time
    sku = Service.create_sku("SKU-001", "Widget", 100)

    with_past = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=1
    )
    time.sleep(1.1)

    with pytest.raises(ReservationExpiredError):
        Service.confirm_reservation(with_past["id"])


def test_confirm_reservation_not_found():
    with pytest.raises(ReservationNotFoundError):
        Service.confirm_reservation(999)


def test_confirm_reservation_already_confirmed():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    reservation = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    Service.confirm_reservation(reservation["id"])

    with pytest.raises(InvalidStateTransitionError):
        Service.confirm_reservation(reservation["id"])


def test_cancel_reservation_pending():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    reservation = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    cancelled = Service.cancel_reservation(reservation["id"])
    assert cancelled["status"] == ReservationStatus.CANCELLED.value


def test_cancel_reservation_confirmed_restores_stock():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    reservation = Service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    Service.confirm_reservation(reservation["id"])

    sku_after_confirm = Service.adjust_stock(sku["id"], 0)
    assert sku_after_confirm["current_stock"] == 90

    Service.cancel_reservation(reservation["id"])
    sku_after_cancel = Service.adjust_stock(sku["id"], 0)
    assert sku_after_cancel["current_stock"] == 100


def test_cancel_reservation_not_found():
    with pytest.raises(ReservationNotFoundError):
        Service.cancel_reservation(999)


def test_list_orders():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    res1 = Service.create_reservation(sku["id"], 10, "idempotency-1", ttl_seconds=3600)
    res2 = Service.create_reservation(sku["id"], 5, "idempotency-2", ttl_seconds=3600)

    Service.confirm_reservation(res1["id"])
    Service.confirm_reservation(res2["id"])

    orders, total = Service.list_orders(offset=0, limit=20)
    assert total == 2
    assert len(orders) == 2
    assert orders[0]["quantity"] == 5
    assert orders[1]["quantity"] == 10


def test_list_orders_pagination():
    sku = Service.create_sku("SKU-001", "Widget", 100)
    for i in range(5):
        res = Service.create_reservation(sku["id"], i + 1, f"idempotency-{i}", ttl_seconds=3600)
        Service.confirm_reservation(res["id"])

    orders1, total = Service.list_orders(offset=0, limit=2)
    assert len(orders1) == 2
    assert total == 5

    orders2, total = Service.list_orders(offset=2, limit=2)
    assert len(orders2) == 2
    assert total == 5
