import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from src.commerce_service.service import CommerceService
from src.commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def repository(temp_db):
    return Repository(db_path=temp_db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100


def test_adjust_stock_positive(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 50)
    assert result["available_stock"] == 150


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -30)
    assert result["available_stock"] == 70


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 50, "key1")
    assert result["status"] == "PENDING"
    assert result["quantity"] == 50
    assert result["sku"] == "SKU001"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 30)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 50, "key1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 50, "key1")
    result2 = service.create_reservation("SKU001", 50, "key1")
    assert result1["id"] == result2["id"]


def test_idempotent_no_double_deduction(service):
    service.create_sku("SKU001", 100)
    service.create_reservation("SKU001", 50, "key1")
    service.create_reservation("SKU001", 50, "key1")

    stock = service.repo.get_sku_stock("SKU001")
    assert stock == 50


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key1")
    order = service.confirm_reservation(res["id"])
    assert order["reservation_id"] == res["id"]
    assert "id" in order
    assert "created_at" in order


def test_confirm_reservation_not_found(service):
    with pytest.raises(ValueError, match="Reservation not found"):
        service.confirm_reservation("nonexistent")


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key1")
    service.confirm_reservation(res["id"])

    with pytest.raises(ValueError, match="not PENDING"):
        service.confirm_reservation(res["id"])


def test_confirm_reservation_expired(service, temp_db):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key1")

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    past = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    cursor.execute(
        'UPDATE reservations SET created_at = ? WHERE id = ?',
        (past, res["id"])
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res["id"])

    reservation = service.repo.get_reservation(res["id"])
    assert reservation["status"] == "EXPIRED"

    stock = service.repo.get_sku_stock("SKU001")
    assert stock == 100


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key1")
    result = service.cancel_reservation(res["id"])
    assert result["status"] == "CANCELLED"

    stock = service.repo.get_sku_stock("SKU001")
    assert stock == 100


def test_cancel_reservation_restores_stock(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key1")

    stock_after_reserve = service.repo.get_sku_stock("SKU001")
    assert stock_after_reserve == 50

    service.cancel_reservation(res["id"])

    stock_after_cancel = service.repo.get_sku_stock("SKU001")
    assert stock_after_cancel == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key1")
    service.confirm_reservation(res["id"])

    with pytest.raises(ValueError, match="not PENDING"):
        service.cancel_reservation(res["id"])


def test_get_orders_empty(service):
    result = service.get_orders()
    assert result["orders"] == []
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 0


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(15):
        res = service.create_reservation("SKU001", 10, f"key{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert len(page1["orders"]) == 10
    assert page1["page"] == 1
    assert page1["total"] == 15

    page2 = service.get_orders(page=2, size=10)
    assert len(page2["orders"]) == 5
    assert page2["page"] == 2
    assert page2["total"] == 15


def test_happy_path_sku_reserve_confirm_order(service):
    service.create_sku("SKU001", 100)

    res = service.create_reservation("SKU001", 50, "key1")
    assert res["status"] == "PENDING"

    order = service.confirm_reservation(res["id"])
    assert order["reservation_id"] == res["id"]

    orders = service.get_orders()
    assert len(orders["orders"]) == 1
    assert orders["orders"][0]["id"] == order["id"]
