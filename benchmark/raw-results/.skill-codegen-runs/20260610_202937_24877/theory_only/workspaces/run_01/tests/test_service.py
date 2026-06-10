import pytest
import os
from datetime import datetime, timedelta
from commerce_service.repository import SQLiteRepository
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    db_path = "test_commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    repository = SQLiteRepository(db_path=db_path)
    yield repository
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100
    assert "id" in result


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", 10)
    assert result["available_stock"] == 110

    result = service.adjust_stock("SKU-001", -20)
    assert result["available_stock"] == 90


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation("SKU-001", 20, "idempotency-1")
    assert result["sku"] == "SKU-001"
    assert result["quantity"] == 20
    assert result["status"] == "PENDING"
    assert result["idempotency_key"] == "idempotency-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 20, "idempotency-1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    result1 = service.create_reservation("SKU-001", 20, "idempotency-1")
    result2 = service.create_reservation("SKU-001", 20, "idempotency-1")

    assert result1["id"] == result2["id"]
    assert result1["sku"] == result2["sku"]
    assert result1["quantity"] == result2["quantity"]

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku["available_stock"] == 80


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 20, "idempotency-1")

    result = service.confirm_reservation(reservation["id"])
    assert result["status"] == "CONFIRMED"

    order = service.repo.get_order_by_reservation_id(reservation["id"])
    assert order is not None


def test_confirm_reservation_expired(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 20, "idempotency-1")

    conn = service.repo._get_connection()
    cursor = conn.cursor()
    old_time = datetime.utcnow() - timedelta(seconds=301)
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation["id"]),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation["id"])

    updated = service.repo.get_reservation_by_id(reservation["id"])
    assert updated["status"] == "EXPIRED"

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku["available_stock"] == 100


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 20, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="not in PENDING"):
        service.confirm_reservation(reservation["id"])


def test_cancel_reservation(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 20, "idempotency-1")

    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "CANCELLED"

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 20, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="not in PENDING"):
        service.cancel_reservation(reservation["id"])


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 100)

    for i in range(15):
        reservation = service.create_reservation("SKU-001", 1, f"idempotency-{i}")
        service.confirm_reservation(reservation["id"])

    result = service.get_orders(page=1, size=10)
    assert len(result["items"]) == 10
    assert result["total"] == 15
    assert result["page"] == 1
    assert result["size"] == 10

    result = service.get_orders(page=2, size=10)
    assert len(result["items"]) == 5
    assert result["total"] == 15
    assert result["page"] == 2
