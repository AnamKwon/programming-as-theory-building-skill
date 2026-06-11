"""Tests for the service business logic layer."""

import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from src.commerce_service.repository import Database, Repository
from src.commerce_service.service import Service


@pytest.fixture
def service():
    db = Database(":memory:")
    db.init_db()
    repository = Repository(db)
    return Service(repository), repository


def test_create_sku(service):
    svc, repo = service
    result = svc.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["stock"] == 100
    assert result["id"] == 1


def test_create_duplicate_sku(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    with pytest.raises(HTTPException) as exc:
        svc.create_sku("SKU001", 50)
    assert exc.value.status_code == 400


def test_adjust_stock_increase(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    result = svc.adjust_stock("SKU001", 50)
    assert result["stock"] == 150


def test_adjust_stock_decrease(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    result = svc.adjust_stock("SKU001", -30)
    assert result["stock"] == 70


def test_adjust_stock_nonexistent_sku(service):
    svc, repo = service
    with pytest.raises(HTTPException) as exc:
        svc.adjust_stock("INVALID", 10)
    assert exc.value.status_code == 404


def test_create_reservation_happy_path(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    result = svc.create_reservation("SKU001", 30, "idempotency-1")
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"
    sku = repo.get_sku_by_name("SKU001")
    assert sku["stock"] == 70


def test_create_reservation_insufficient_stock(service):
    svc, repo = service
    svc.create_sku("SKU001", 50)
    with pytest.raises(HTTPException) as exc:
        svc.create_reservation("SKU001", 100, "idempotency-1")
    assert exc.value.status_code == 400
    assert "Insufficient stock" in str(exc.value.detail)


def test_create_reservation_idempotency(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    result1 = svc.create_reservation("SKU001", 30, "idempotency-1")
    result2 = svc.create_reservation("SKU001", 30, "idempotency-1")
    assert result1["id"] == result2["id"]
    sku = repo.get_sku_by_name("SKU001")
    assert sku["stock"] == 70


def test_create_reservation_nonexistent_sku(service):
    svc, repo = service
    with pytest.raises(HTTPException) as exc:
        svc.create_reservation("INVALID", 10, "idempotency-1")
    assert exc.value.status_code == 404


def test_confirm_reservation_happy_path(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    res = svc.create_reservation("SKU001", 30, "idempotency-1")
    order = svc.confirm_reservation(res["id"])
    assert order["reservation_id"] == res["id"]
    reservation = repo.get_reservation_by_id(res["id"])
    assert reservation["status"] == "CONFIRMED"


def test_confirm_reservation_not_pending(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    res = svc.create_reservation("SKU001", 30, "idempotency-1")
    svc.confirm_reservation(res["id"])
    with pytest.raises(HTTPException) as exc:
        svc.confirm_reservation(res["id"])
    assert exc.value.status_code == 400
    assert "not PENDING" in str(exc.value.detail)


def test_confirm_reservation_expired(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    res = svc.create_reservation("SKU001", 30, "idempotency-1")
    repo.update_reservation_status(res["id"], "PENDING")
    old_time = (datetime.now(timezone.utc) - __import__('datetime').timedelta(seconds=400)).replace(tzinfo=None)
    with repo.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time.isoformat(), res["id"])
        )
        conn.commit()
    with pytest.raises(HTTPException) as exc:
        svc.confirm_reservation(res["id"])
    assert exc.value.status_code == 400
    assert "expired" in str(exc.value.detail)
    sku = repo.get_sku_by_name("SKU001")
    assert sku["stock"] == 100


def test_confirm_reservation_nonexistent(service):
    svc, repo = service
    with pytest.raises(HTTPException) as exc:
        svc.confirm_reservation(9999)
    assert exc.value.status_code == 404


def test_cancel_reservation_happy_path(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    res = svc.create_reservation("SKU001", 30, "idempotency-1")
    svc.cancel_reservation(res["id"])
    reservation = repo.get_reservation_by_id(res["id"])
    assert reservation["status"] == "CANCELLED"
    sku = repo.get_sku_by_name("SKU001")
    assert sku["stock"] == 100


def test_cancel_reservation_not_pending(service):
    svc, repo = service
    svc.create_sku("SKU001", 100)
    res = svc.create_reservation("SKU001", 30, "idempotency-1")
    svc.confirm_reservation(res["id"])
    with pytest.raises(HTTPException) as exc:
        svc.cancel_reservation(res["id"])
    assert exc.value.status_code == 400


def test_cancel_reservation_nonexistent(service):
    svc, repo = service
    with pytest.raises(HTTPException) as exc:
        svc.cancel_reservation(9999)
    assert exc.value.status_code == 404


def test_list_orders_pagination(service):
    svc, repo = service
    svc.create_sku("SKU001", 1000)
    for i in range(15):
        res = svc.create_reservation("SKU001", 10, f"idempotency-{i}")
        svc.confirm_reservation(res["id"])
    result = svc.list_orders(page=1, size=10)
    assert len(result["items"]) == 10
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 15
    result = svc.list_orders(page=2, size=10)
    assert len(result["items"]) == 5
    assert result["page"] == 2
