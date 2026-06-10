import pytest
import os
from datetime import datetime, timezone, timedelta
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    db_path = "test_commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    db = Database(db_path=db_path)
    yield db

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def service(test_db):
    return CommerceService(test_db)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 10)
    assert result["available_stock"] == 110

    result = service.adjust_stock("SKU001", -20)
    assert result["available_stock"] == 90


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 50)

    with pytest.raises(Exception) as exc_info:
        service.create_reservation("SKU001", 100, "key1")
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 30, "key1")

    assert result["id"] is not None
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"

    stock = service.db.get_sku_stock("SKU001")
    assert stock == 70


def test_create_reservation_idempotent(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 30, "key1")
    stock_after_first = service.db.get_sku_stock("SKU001")

    result2 = service.create_reservation("SKU001", 30, "key1")
    stock_after_second = service.db.get_sku_stock("SKU001")

    assert result1["id"] == result2["id"]
    assert result1["created_at"] == result2["created_at"]
    assert stock_after_first == stock_after_second == 70


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "key1")

    result = service.confirm_reservation(reservation["id"])
    assert result["status"] == "CONFIRMED"
    assert result["order_id"] is not None

    order = service.db.get_orders()[0][0]
    assert order["sku"] == "SKU001"
    assert order["quantity"] == 30


def test_confirm_reservation_expired(service, test_db):
    service.create_sku("SKU001", 100)

    now = datetime.now(timezone.utc).isoformat()
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()

    test_db.create_reservation("SKU001", 30, "key1")
    reservation_id = test_db.get_reservation_by_idempotency_key("key1")["id"]

    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation_id)
    assert "Reservation expired" in str(exc_info.value)

    reservation = service.db.get_reservation(reservation_id)
    assert reservation["status"] == "EXPIRED"

    stock = service.db.get_sku_stock("SKU001")
    assert stock == 100


def test_confirm_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "key1")

    service.confirm_reservation(reservation["id"])

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert "not pending" in str(exc_info.value)


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 30, "key1")

    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "CANCELLED"
    assert result["restored_stock"] == 30

    stock = service.db.get_sku_stock("SKU001")
    assert stock == 100


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(15):
        res = service.create_reservation("SKU001", 10, f"key{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert len(page1["items"]) == 10
    assert page1["total"] == 15
    assert page1["page"] == 1

    page2 = service.get_orders(page=2, size=10)
    assert len(page2["items"]) == 5
    assert page2["total"] == 15
    assert page2["page"] == 2
