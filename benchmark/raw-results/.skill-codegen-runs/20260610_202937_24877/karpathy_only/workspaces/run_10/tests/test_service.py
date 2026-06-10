import pytest
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from commerce_service.service import CommerceService
from commerce_service.repository import init_db, DATABASE_PATH


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    init_db()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest.fixture
def service():
    return CommerceService()


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert result["id"] is not None


def test_create_duplicate_sku(service):
    service.create_sku("SKU001", 100)
    with pytest.raises(Exception):
        service.create_sku("SKU001", 50)


def test_adjust_stock_increase(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 50)
    assert result["sku"] == "SKU001"
    assert result["updated_stock"] == 150


def test_adjust_stock_decrease(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -30)
    assert result["updated_stock"] == 70


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(Exception):
        service.adjust_stock("NONEXISTENT", 10)


def test_adjust_stock_negative_result(service):
    service.create_sku("SKU001", 50)
    with pytest.raises(Exception):
        service.adjust_stock("SKU001", -100)


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 30, "idempotency-1")
    assert result["id"] is not None
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"
    assert result["idempotency_key"] == "idempotency-1"


def test_create_reservation_deducts_stock(service):
    service.create_sku("SKU001", 100)
    service.create_reservation("SKU001", 30, "idempotency-1")

    sku_data = service.sku_repo.get_sku_by_name("SKU001")
    assert sku_data["available_stock"] == 70


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 20)
    with pytest.raises(Exception) as exc_info:
        service.create_reservation("SKU001", 30, "idempotency-1")
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 30, "idempotency-1")
    result2 = service.create_reservation("SKU001", 30, "idempotency-1")

    assert result1["id"] == result2["id"]
    assert result1["quantity"] == result2["quantity"]

    sku_data = service.sku_repo.get_sku_by_name("SKU001")
    assert sku_data["available_stock"] == 70


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    result = service.confirm_reservation(reservation["id"])

    assert result["status"] == "CONFIRMED"
    assert result["order_id"] is not None


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert "not pending" in str(exc_info.value)


def test_confirm_reservation_nonexistent(service):
    with pytest.raises(Exception):
        service.confirm_reservation(999)


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")

    sku_before = service.sku_repo.get_sku_by_name("SKU001")
    assert sku_before["available_stock"] == 70

    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "CANCELLED"
    assert result["restored_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(Exception) as exc_info:
        service.cancel_reservation(reservation["id"])
    assert "not pending" in str(exc_info.value)


def test_reservation_expiry(service):
    service.create_sku("SKU001", 100)

    # Manually create an old reservation
    from commerce_service.repository import _get_connection
    conn = _get_connection()
    cursor = conn.cursor()

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    cursor.execute(
        """INSERT INTO reservations (sku_id, sku, quantity, status, idempotency_key, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, "SKU001", 30, "PENDING", "old-key", old_time)
    )
    conn.commit()
    reservation_id = cursor.lastrowid
    conn.close()

    # Manually deduct stock
    service.sku_repo.update_stock(1, 70)

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation_id)
    assert "expired" in str(exc_info.value)

    # Verify stock was restored
    sku_data = service.sku_repo.get_sku_by_name("SKU001")
    assert sku_data["available_stock"] == 100

    # Verify status is EXPIRED
    reservation = service.reservation_repo.get_reservation_by_id(reservation_id)
    assert reservation["status"] == "EXPIRED"


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    # Create multiple reservations and confirm them
    for i in range(25):
        res = service.create_reservation("SKU001", 1, f"key-{i}")
        service.confirm_reservation(res["id"])

    result_page1 = service.get_orders(1, 10)
    assert len(result_page1["orders"]) == 10
    assert result_page1["page"] == 1
    assert result_page1["size"] == 10
    assert result_page1["total"] == 25

    result_page2 = service.get_orders(2, 10)
    assert len(result_page2["orders"]) == 10
    assert result_page2["page"] == 2

    result_page3 = service.get_orders(3, 10)
    assert len(result_page3["orders"]) == 5
    assert result_page3["page"] == 3


def test_happy_path_workflow(service):
    # Create SKU
    service.create_sku("SKU001", 100)

    # Reserve stock
    res = service.create_reservation("SKU001", 30, "idempotency-1")
    assert res["status"] == "PENDING"

    # Confirm reservation
    confirm_result = service.confirm_reservation(res["id"])
    assert confirm_result["status"] == "CONFIRMED"
    order_id = confirm_result["order_id"]

    # Get orders
    orders_result = service.get_orders(1, 10)
    assert orders_result["total"] == 1
    assert orders_result["orders"][0]["id"] == order_id

    # Verify final stock
    sku_data = service.sku_repo.get_sku_by_name("SKU001")
    assert sku_data["available_stock"] == 70
