import pytest
from datetime import datetime, timezone, timedelta
from src.commerce_service.repository import Repository
from src.commerce_service.service import Service


@pytest.fixture
def repo():
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    return Service(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert "id" in result


def test_adjust_stock_positive(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 50)
    assert result["available_stock"] == 150


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -30)
    assert result["available_stock"] == 70


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 30, "idempotency-1")
    assert result["id"] is not None
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"
    assert "created_at" in result

    sku = service.repository.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 70


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 20)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 30, "idempotency-1")

    sku = service.repository.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 20


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 30, "idempotency-1")
    result2 = service.create_reservation("SKU001", 30, "idempotency-1")

    assert result1["id"] == result2["id"]

    sku = service.repository.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 70


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "idempotency-1")
    confirmed = service.confirm_reservation(res["id"])

    assert confirmed["status"] == "CONFIRMED"

    order = service.repository.get_orders(0, 10)
    assert len(order) == 1
    assert order[0]["reservation_id"] == res["id"]


def test_confirm_expired_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "idempotency-1")

    old_created_at = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    service.repository.update_reservation_status(res["id"], "PENDING")
    import sqlite3
    with sqlite3.connect(service.repository.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_created_at, res["id"])
        )
        conn.commit()

    with pytest.raises(ValueError, match="Reservation expired"):
        service.confirm_reservation(res["id"])

    updated_res = service.repository.get_reservation(res["id"])
    assert updated_res["status"] == "EXPIRED"

    sku = service.repository.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 100


def test_confirm_non_pending_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "idempotency-1")
    service.repository.update_reservation_status(res["id"], "CANCELLED")

    with pytest.raises(ValueError, match="not in PENDING status"):
        service.confirm_reservation(res["id"])


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "idempotency-1")

    sku_before = service.repository.get_sku_by_name("SKU001")
    assert sku_before["available_stock"] == 70

    cancelled = service.cancel_reservation(res["id"])
    assert cancelled["status"] == "CANCELLED"

    sku_after = service.repository.get_sku_by_name("SKU001")
    assert sku_after["available_stock"] == 100


def test_cancel_non_pending_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "idempotency-1")
    service.confirm_reservation(res["id"])

    with pytest.raises(ValueError, match="not in PENDING status"):
        service.cancel_reservation(res["id"])


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU001", 10, f"idem-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(1, 10)
    assert len(page1) == 10

    page2 = service.get_orders(2, 10)
    assert len(page2) == 10

    page3 = service.get_orders(3, 10)
    assert len(page3) == 5

    page4 = service.get_orders(4, 10)
    assert len(page4) == 0
