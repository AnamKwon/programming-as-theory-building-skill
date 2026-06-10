import pytest
import os
from datetime import datetime, timedelta
from commerce_service.service import SKUService, ReservationService
from commerce_service.repository import (
    init_db,
    SKURepository,
    ReservationRepository,
    OrderRepository,
    DB_PATH,
)


@pytest.fixture(autouse=True)
def setup_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def test_create_sku():
    sku = SKUService.create_sku("SKU001", 100)
    assert sku["sku_id"] == "SKU001"
    assert sku["stock"] == 100


def test_create_duplicate_sku():
    SKUService.create_sku("SKU001", 100)
    with pytest.raises(Exception) as exc_info:
        SKUService.create_sku("SKU001", 50)
    assert "already exists" in str(exc_info.value)


def test_adjust_stock():
    SKUService.create_sku("SKU001", 100)
    result = SKUService.adjust_stock("SKU001", 10)
    assert result["stock"] == 110

    result = SKUService.adjust_stock("SKU001", -20)
    assert result["stock"] == 90


def test_adjust_stock_nonexistent():
    with pytest.raises(Exception) as exc_info:
        SKUService.adjust_stock("NOSKU", 10)
    assert "not found" in str(exc_info.value)


def test_adjust_stock_negative():
    SKUService.create_sku("SKU001", 10)
    with pytest.raises(Exception) as exc_info:
        SKUService.adjust_stock("SKU001", -20)
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_success():
    SKUService.create_sku("SKU001", 100)
    res = ReservationService.create_reservation("SKU001", 50, "idempotency-key-1")
    assert res["sku_id"] == "SKU001"
    assert res["quantity"] == 50
    assert res["status"] == "pending"


def test_create_reservation_idempotent():
    SKUService.create_sku("SKU001", 100)
    res1 = ReservationService.create_reservation("SKU001", 50, "idempotency-key-1")
    res2 = ReservationService.create_reservation("SKU001", 50, "idempotency-key-1")
    assert res1["reservation_id"] == res2["reservation_id"]


def test_create_reservation_insufficient_stock():
    SKUService.create_sku("SKU001", 100)
    with pytest.raises(Exception) as exc_info:
        ReservationService.create_reservation("SKU001", 101, "idempotency-key-1")
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_with_pending_reservation():
    SKUService.create_sku("SKU001", 100)
    ReservationService.create_reservation("SKU001", 60, "idempotency-key-1")
    with pytest.raises(Exception) as exc_info:
        ReservationService.create_reservation("SKU001", 50, "idempotency-key-2")
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_nonexistent_sku():
    with pytest.raises(Exception) as exc_info:
        ReservationService.create_reservation("NOSKU", 50, "idempotency-key-1")
    assert "not found" in str(exc_info.value)


def test_confirm_reservation():
    SKUService.create_sku("SKU001", 100)
    res = ReservationService.create_reservation("SKU001", 50, "idempotency-key-1")
    confirmed = ReservationService.confirm_reservation(res["reservation_id"])
    assert confirmed["status"] == "confirmed"

    order = OrderRepository.get_by_reservation_id(res["reservation_id"])
    assert order is not None
    assert order["status"] == "confirmed"


def test_confirm_expired_reservation():
    SKUService.create_sku("SKU001", 100)
    res_id = ReservationRepository.create("SKU001", 50, "idempotency-key-1")["reservation_id"]

    expires_at = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    import sqlite3
    conn = sqlite3.connect("commerce.db")
    c = conn.cursor()
    c.execute("UPDATE reservations SET expires_at = ? WHERE reservation_id = ?", (expires_at, res_id))
    conn.commit()
    conn.close()

    with pytest.raises(Exception) as exc_info:
        ReservationService.confirm_reservation(res_id)
    assert "expired" in str(exc_info.value)


def test_cancel_reservation():
    SKUService.create_sku("SKU001", 100)
    res = ReservationService.create_reservation("SKU001", 50, "idempotency-key-1")
    cancelled = ReservationService.cancel_reservation(res["reservation_id"])
    assert cancelled["status"] == "cancelled"


def test_cancel_nonexistent_reservation():
    with pytest.raises(Exception) as exc_info:
        ReservationService.cancel_reservation("nonexistent")
    assert "not found" in str(exc_info.value)
