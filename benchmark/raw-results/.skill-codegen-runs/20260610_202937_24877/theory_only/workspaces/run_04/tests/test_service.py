import pytest
import os
from datetime import datetime, timedelta
import sqlite3
from src.commerce_service.repository import Repository, get_db_connection, init_db
from src.commerce_service.service import CommerceService
from fastapi import HTTPException

DATABASE_FILE = "commerce_test.db"


@pytest.fixture(autouse=True)
def setup_test_db():
    os.environ["DATABASE_FILE"] = DATABASE_FILE
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
    init_db()
    yield
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)


@pytest.fixture
def repository():
    return Repository()


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100


def test_create_duplicate_sku(service):
    service.create_sku("SKU-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_sku("SKU-001", 50)
    assert exc_info.value.status_code == 400


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", 50)
    assert result["available_stock"] == 150

    result = service.adjust_stock("SKU-001", -30)
    assert result["available_stock"] == 120


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    result, status = service.create_reservation("SKU-001", 30, "key-1")
    assert status == 201
    assert result["id"] == 1
    assert result["sku"] == "SKU-001"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"

    sku = service.repo.get_sku("SKU-001")
    assert sku["available_stock"] == 70


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("SKU-001", 150, "key-1")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_idempotent_reservation(service):
    service.create_sku("SKU-001", 100)
    result1, status1 = service.create_reservation("SKU-001", 30, "key-1")
    result2, status2 = service.create_reservation("SKU-001", 30, "key-1")

    assert status1 == 201
    assert status2 == 200
    assert result1["id"] == result2["id"]

    sku = service.repo.get_sku("SKU-001")
    assert sku["available_stock"] == 70


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    result, _ = service.create_reservation("SKU-001", 30, "key-1")

    confirmed = service.confirm_reservation(result["id"])
    assert confirmed["status"] == "PENDING"

    updated = service.repo.get_reservation(result["id"])
    assert updated["status"] == "CONFIRMED"

    orders, _ = service.repo.get_orders()
    assert len(orders) == 1
    assert orders[0]["sku"] == "SKU-001"
    assert orders[0]["quantity"] == 30


def test_confirm_expired_reservation(service):
    service.create_sku("SKU-001", 100)
    result, _ = service.create_reservation("SKU-001", 30, "key-1")

    reservation_id = result["id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    old_time = (datetime.utcnow() - timedelta(seconds=350)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id)
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation_id)
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()

    updated = service.repo.get_reservation(reservation_id)
    assert updated["status"] == "EXPIRED"

    sku = service.repo.get_sku("SKU-001")
    assert sku["available_stock"] == 100


def test_confirm_non_pending_reservation(service):
    service.create_sku("SKU-001", 100)
    result, _ = service.create_reservation("SKU-001", 30, "key-1")

    service.repo.update_reservation_status(result["id"], "CANCELLED")

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(result["id"])
    assert exc_info.value.status_code == 400


def test_cancel_reservation_success(service):
    service.create_sku("SKU-001", 100)
    result, _ = service.create_reservation("SKU-001", 30, "key-1")

    cancelled = service.cancel_reservation(result["id"])
    assert cancelled["status"] == "PENDING"

    updated = service.repo.get_reservation(result["id"])
    assert updated["status"] == "CANCELLED"

    sku = service.repo.get_sku("SKU-001")
    assert sku["available_stock"] == 100


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 1000)

    for i in range(25):
        result, _ = service.create_reservation("SKU-001", 10, f"key-{i}")
        service.confirm_reservation(result["id"])

    result1 = service.get_orders(page=1, size=10)
    assert len(result1["orders"]) == 10
    assert result1["page"] == 1
    assert result1["size"] == 10
    assert result1["total"] == 25

    result2 = service.get_orders(page=2, size=10)
    assert len(result2["orders"]) == 10
    assert result2["page"] == 2

    result3 = service.get_orders(page=3, size=10)
    assert len(result3["orders"]) == 5
    assert result3["page"] == 3
