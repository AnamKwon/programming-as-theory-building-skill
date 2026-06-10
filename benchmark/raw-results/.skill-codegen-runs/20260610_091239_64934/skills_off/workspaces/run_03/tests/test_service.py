import pytest
import tempfile
import os
from datetime import datetime, timedelta

from commerce_service.repository import Database
from commerce_service.service import CommerceService
from commerce_service.models import ReservationStatus, OrderStatus


@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def service(temp_db):
    return CommerceService(temp_db)


def test_create_sku(service):
    result = service.create_sku("SKU001", "Product 1", 100)
    assert result["code"] == "SKU001"
    assert result["name"] == "Product 1"
    assert result["current_stock"] == 100
    assert result["reserved_stock"] == 0


def test_create_sku_duplicate(service):
    service.create_sku("SKU001", "Product 1", 100)
    with pytest.raises(Exception):
        service.create_sku("SKU001", "Product 2", 50)


def test_adjust_stock(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    result = service.adjust_stock(sku["id"], 50)
    assert result["current_stock"] == 150


def test_adjust_stock_negative(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    result = service.adjust_stock(sku["id"], -30)
    assert result["current_stock"] == 70


def test_adjust_stock_not_found(service):
    with pytest.raises(Exception):
        service.adjust_stock(999, 50)


def test_create_reservation_success(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    assert reservation["sku_id"] == sku["id"]
    assert reservation["quantity"] == 10
    assert reservation["status"] == ReservationStatus.PENDING.value
    assert reservation["idempotency_key"] == "key-1"


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU001", "Product 1", 10)
    with pytest.raises(Exception) as exc_info:
        service.create_reservation(sku["id"], 20, "key-1")
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_idempotency(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation1 = service.create_reservation(sku["id"], 10, "key-1")
    reservation2 = service.create_reservation(sku["id"], 10, "key-1")
    assert reservation1["id"] == reservation2["id"]


def test_create_reservation_multiple_on_same_sku(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    res1 = service.create_reservation(sku["id"], 10, "key-1")
    res2 = service.create_reservation(sku["id"], 20, "key-2")
    assert res1["id"] != res2["id"]


def test_create_reservation_depletes_available_stock(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    service.create_reservation(sku["id"], 50, "key-1")
    with pytest.raises(Exception) as exc_info:
        service.create_reservation(sku["id"], 60, "key-2")
    assert "Insufficient stock" in str(exc_info.value)


def test_confirm_reservation(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    confirmed = service.confirm_reservation(reservation["id"])
    assert confirmed["status"] == ReservationStatus.CONFIRMED.value


def test_confirm_reservation_not_found(service):
    with pytest.raises(Exception):
        service.confirm_reservation(999)


def test_confirm_reservation_already_confirmed(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    service.confirm_reservation(reservation["id"])
    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert "cannot confirm" in str(exc_info.value)


def test_confirm_reservation_reduces_stock(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    service.confirm_reservation(reservation["id"])
    updated_sku = service.db.get_sku(sku["id"])
    assert updated_sku["current_stock"] == 90
    assert updated_sku["reserved_stock"] == 0


def test_cancel_reservation(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    cancelled = service.cancel_reservation(reservation["id"])
    assert cancelled["status"] == ReservationStatus.CANCELLED.value


def test_cancel_reservation_not_found(service):
    with pytest.raises(Exception):
        service.cancel_reservation(999)


def test_cancel_reservation_releases_reserved_stock(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    service.cancel_reservation(reservation["id"])
    updated_sku = service.db.get_sku(sku["id"])
    assert updated_sku["current_stock"] == 100
    assert updated_sku["reserved_stock"] == 0


def test_get_order(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation = service.create_reservation(sku["id"], 10, "key-1")
    service.confirm_reservation(reservation["id"])
    orders = service.db.list_orders(0, 10)
    assert len(orders[0]) == 1
    order = orders[0][0]
    retrieved = service.get_order(order["id"])
    assert retrieved["sku_id"] == sku["id"]


def test_get_order_not_found(service):
    with pytest.raises(Exception):
        service.get_order(999)


def test_list_orders_pagination(service):
    sku = service.create_sku("SKU001", "Product 1", 200)
    for i in range(5):
        reservation = service.create_reservation(sku["id"], 10, f"key-{i}")
        service.confirm_reservation(reservation["id"])

    page1 = service.list_orders(0, 2)
    assert len(page1["items"]) == 2
    assert page1["total"] == 5
    assert page1["offset"] == 0

    page2 = service.list_orders(2, 2)
    assert len(page2["items"]) == 2
    assert page2["total"] == 5
    assert page2["offset"] == 2


def test_expired_reservation_cannot_be_confirmed(service):
    sku = service.create_sku("SKU001", "Product 1", 100)
    reservation_id = service.db.create_reservation(sku["id"], 10, "key-1")
    old_reservation = service.db.get_reservation(reservation_id)

    old_expires = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    import sqlite3
    with service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (old_expires, reservation_id),
        )

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation_id)
    assert "expired" in str(exc_info.value).lower()
