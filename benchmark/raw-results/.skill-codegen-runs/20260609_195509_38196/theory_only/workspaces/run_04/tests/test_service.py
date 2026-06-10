import pytest
from datetime import datetime, timedelta, UTC
from commerce_service.repository import Database
from commerce_service.service import CommerceService
from fastapi import HTTPException


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["id"] == 1
    assert result["name"] == "SKU-001"
    assert result["quantity_available"] == 100


def test_adjust_stock_increase(service):
    service.create_sku("SKU-001", 50)
    result = service.adjust_stock(1, 25)
    assert result["quantity_available"] == 75


def test_adjust_stock_decrease(service):
    service.create_sku("SKU-001", 50)
    result = service.adjust_stock(1, -20)
    assert result["quantity_available"] == 30


def test_adjust_stock_insufficient(service):
    service.create_sku("SKU-001", 50)
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(1, -60)
    assert exc_info.value.status_code == 400


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(999, 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")
    assert result["id"] == 1
    assert result["sku_id"] == 1
    assert result["quantity"] == 50
    assert result["status"] == "pending"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(1, 50, "key-1")
    assert exc_info.value.status_code == 409
    assert "Insufficient" in exc_info.value.detail


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    result1 = service.create_reservation(1, 50, "idempotency-key-1")
    result2 = service.create_reservation(1, 50, "idempotency-key-1")
    assert result1["id"] == result2["id"]


def test_create_reservation_idempotency_conflict_confirmed(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation(1, 50, "key-1")
    service.confirm_reservation(res["id"])
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(1, 50, "key-1")
    assert exc_info.value.status_code == 409


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation(1, 50, "key-1")
    result = service.confirm_reservation(res["id"])
    assert result["status"] == "confirmed"


def test_confirm_reservation_expired(service, db):
    service.create_sku("SKU-001", 100)
    res_id = db.create_reservation(1, 50, "key-1")
    past_time = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
    db._connection().__enter__().execute(
        "UPDATE reservations SET expires_at = ? WHERE id = ?",
        (past_time, res_id),
    )
    db._connection().__enter__().commit()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(res_id)
    assert exc_info.value.status_code == 409
    assert "expired" in exc_info.value.detail


def test_confirm_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_confirm_reservation_already_confirmed(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation(1, 50, "key-1")
    service.confirm_reservation(res["id"])
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(res["id"])
    assert exc_info.value.status_code == 409


def test_cancel_reservation_success(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation(1, 50, "key-1")
    result = service.cancel_reservation(res["id"])
    assert result["status"] == "cancelled"


def test_cancel_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404


def test_cancel_reservation_already_confirmed(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation(1, 50, "key-1")
    service.confirm_reservation(res["id"])
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(res["id"])
    assert exc_info.value.status_code == 409


def test_get_orders_empty(service):
    result = service.get_orders(page=1, size=10)
    assert result["items"] == []
    assert result["total"] == 0
    assert result["page"] == 1


def test_get_orders_with_confirmed_reservation(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation(1, 50, "key-1")
    service.confirm_reservation(res["id"])
    result = service.get_orders(page=1, size=10)
    assert len(result["items"]) == 1
    assert result["items"][0]["quantity"] == 50
    assert result["total"] == 1


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 1000)
    for i in range(15):
        res = service.create_reservation(1, 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    result1 = service.get_orders(page=1, size=10)
    assert len(result1["items"]) == 10
    assert result1["total"] == 15
    assert result1["page"] == 1

    result2 = service.get_orders(page=2, size=10)
    assert len(result2["items"]) == 5
    assert result2["page"] == 2


def test_get_orders_invalid_pagination(service):
    with pytest.raises(HTTPException):
        service.get_orders(page=0, size=10)
    with pytest.raises(HTTPException):
        service.get_orders(page=1, size=0)
