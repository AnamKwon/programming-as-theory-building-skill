import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from fastapi import HTTPException


@pytest.fixture
def repository():
    return Repository(":memory:")


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100


def test_adjust_stock_positive(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", 50)
    assert result["available_stock"] == 150


def test_adjust_stock_negative(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", -30)
    assert result["available_stock"] == 70


def test_adjust_stock_nonexistent(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    assert result["id"]
    assert result["sku"] == "SKU-001"
    assert result["quantity"] == 50
    assert result["status"] == "PENDING"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("SKU-001", 50, "idempotency-key-1")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    result1 = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    result2 = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    assert result1["id"] == result2["id"]
    assert result1 == result2
    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku["available_stock"] == 50


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    order = service.confirm_reservation(reservation["id"])
    assert order["id"]
    assert order["reservation_id"] == reservation["id"]


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert exc_info.value.status_code == 400
    assert "not PENDING" in exc_info.value.detail


def test_confirm_reservation_expired(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

    updated_reservation = service.repo.get_reservation_by_id(reservation["id"])
    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    service.repo.repo.db_url = ":memory:"
    conn = service.repo._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation["id"]),
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()

    updated_res = service.repo.get_reservation_by_id(reservation["id"])
    assert updated_res["status"] == "EXPIRED"

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku["available_stock"] == 100


def test_cancel_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "CANCELLED"
    assert result["restored_quantity"] == 50

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation["id"])
    assert exc_info.value.status_code == 400
    assert "not PENDING" in exc_info.value.detail


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 100)

    for i in range(25):
        reservation = service.create_reservation(
            "SKU-001", 1, f"idempotency-key-{i}"
        )
        service.confirm_reservation(reservation["id"])

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
