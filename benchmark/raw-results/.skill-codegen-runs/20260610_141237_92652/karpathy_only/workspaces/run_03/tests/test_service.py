import pytest
import time
from datetime import datetime
from fastapi import HTTPException
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert result["id"] == 1


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -10)
    assert result["available_stock"] == 90

    result = service.adjust_stock("SKU001", 20)
    assert result["available_stock"] == 110


def test_adjust_stock_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc.value.status_code == 404


def test_create_reservation(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 10, "idem-key-1")
    assert result["id"] == 1
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 10
    assert result["status"] == "PENDING"

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 90


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 10)
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU001", 20, "idem-key-1")
    assert exc.value.status_code == 400
    assert "Insufficient stock" in str(exc.value.detail)


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 10, "idem-key-1")
    result2 = service.create_reservation("SKU001", 10, "idem-key-1")

    assert result1["id"] == result2["id"]
    assert result1 == result2

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 90


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")
    reservation_id = res["id"]

    result = service.confirm_reservation(reservation_id)
    assert result["status"] == "CONFIRMED"

    updated_res = service.repo.get_reservation(reservation_id)
    assert updated_res["status"] == "CONFIRMED"

    orders, total = service.repo.list_orders()
    assert total == 1
    assert orders[0]["reservation_id"] == reservation_id


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")
    reservation_id = res["id"]

    service.confirm_reservation(reservation_id)

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(reservation_id)
    assert exc.value.status_code == 400


def test_confirm_reservation_expired(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")
    reservation_id = res["id"]

    reservation = service.repo.get_reservation(reservation_id)
    created_at = datetime.fromisoformat(reservation["created_at"])
    old_time = (created_at - __import__('datetime').timedelta(seconds=301)).isoformat()

    conn = service.repo._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reservation SET created_at = ? WHERE id = ?", (old_time, reservation_id))
    conn.commit()

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(reservation_id)
    assert exc.value.status_code == 400
    assert "Reservation expired" in str(exc.value.detail)

    updated_res = service.repo.get_reservation(reservation_id)
    assert updated_res["status"] == "EXPIRED"

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 100


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")
    reservation_id = res["id"]

    result = service.cancel_reservation(reservation_id)
    assert result["status"] == "CANCELLED"

    updated_res = service.repo.get_reservation(reservation_id)
    assert updated_res["status"] == "CANCELLED"

    sku = service.repo.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idem-key-1")
    reservation_id = res["id"]

    service.confirm_reservation(reservation_id)

    with pytest.raises(HTTPException) as exc:
        service.cancel_reservation(reservation_id)
    assert exc.value.status_code == 400


def test_list_orders(service):
    service.create_sku("SKU001", 100)
    service.create_sku("SKU002", 100)

    for i in range(15):
        res = service.create_reservation("SKU001", 5, f"idem-key-{i}")
        service.confirm_reservation(res["id"])

    result = service.list_orders(page=1, size=10)
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 15
    assert len(result["orders"]) == 10

    result = service.list_orders(page=2, size=10)
    assert result["page"] == 2
    assert len(result["orders"]) == 5
