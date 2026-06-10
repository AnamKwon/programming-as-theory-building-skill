import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100


def test_create_sku_duplicate(service):
    service.create_sku("SKU001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_sku("SKU001", 50)
    assert exc_info.value.status_code == 400


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 10)
    assert result["available_stock"] == 110

    result = service.adjust_stock("SKU001", -20)
    assert result["available_stock"] == 90


def test_adjust_stock_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 5)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("SKU001", 10, "idem-key-1")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation, status_code = service.create_reservation("SKU001", 25, "idem-key-1")
    assert status_code == 201
    assert reservation["sku"] == "SKU001"
    assert reservation["quantity"] == 25
    assert reservation["status"] == "PENDING"
    assert reservation["idempotency_key"] == "idem-key-1"


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    res1, code1 = service.create_reservation("SKU001", 25, "idem-key-1")
    stock_after_first = service.db.get_sku("SKU001")["available_stock"]

    res2, code2 = service.create_reservation("SKU001", 25, "idem-key-1")
    stock_after_second = service.db.get_sku("SKU001")["available_stock"]

    assert code2 == 200
    assert res1["id"] == res2["id"]
    assert stock_after_first == stock_after_second == 75


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 25, "idem-key-1")

    order = service.confirm_reservation(reservation["id"])
    assert order["reservation_id"] == reservation["id"]
    assert "created_at" in order

    updated_res = service.db.get_reservation(reservation["id"])
    assert updated_res["status"] == "CONFIRMED"


def test_confirm_reservation_expired(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 25, "idem-key-1")

    service.db.conn.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        ((datetime.utcnow() - timedelta(seconds=301)).isoformat(), reservation["id"])
    )
    service.db.conn.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()

    updated_res = service.db.get_reservation(reservation["id"])
    assert updated_res["status"] == "EXPIRED"
    assert service.db.get_sku("SKU001")["available_stock"] == 100


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 25, "idem-key-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert exc_info.value.status_code == 400


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 25, "idem-key-1")
    stock_before = service.db.get_sku("SKU001")["available_stock"]

    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "cancelled"

    updated_res = service.db.get_reservation(reservation["id"])
    assert updated_res["status"] == "CANCELLED"
    assert service.db.get_sku("SKU001")["available_stock"] == stock_before + 25


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 25, "idem-key-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation["id"])
    assert exc_info.value.status_code == 400


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 100)
    for i in range(25):
        res, _ = service.create_reservation("SKU001", 1, f"idem-key-{i}")
        service.confirm_reservation(res["id"])

    result = service.get_orders(page=1, size=10)
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 25
    assert len(result["items"]) == 10

    result = service.get_orders(page=2, size=10)
    assert len(result["items"]) == 10
    assert result["items"][0]["id"] > result["items"][0]["id"]

    result = service.get_orders(page=3, size=10)
    assert len(result["items"]) == 5
