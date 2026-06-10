import pytest
import tempfile
import os
from datetime import datetime, timedelta
from fastapi import HTTPException
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


@pytest.fixture
def repository(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100


def test_adjust_stock_positive(service):
    service.create_sku("SKU001", 50)
    result = service.adjust_stock("SKU001", 25)
    assert result["available_stock"] == 75


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", 50)
    result = service.adjust_stock("SKU001", -20)
    assert result["available_stock"] == 30


def test_adjust_stock_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc.value.status_code == 404


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 10, "idempotency_key_1")
    assert result["id"] is not None
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 10
    assert result["status"] == "PENDING"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 50)
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU001", 100, "key1")
    assert exc.value.status_code == 400
    assert "Insufficient stock" in str(exc.value.detail)


def test_create_reservation_sku_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("NONEXISTENT", 10, "key1")
    assert exc.value.status_code == 404


def test_idempotent_reservation(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 10, "idempotency_key_1")
    result2 = service.create_reservation("SKU001", 10, "idempotency_key_1")

    assert result1["id"] == result2["id"]
    assert result1["sku"] == result2["sku"]
    assert result1["quantity"] == result2["quantity"]

    sku = service.repository.get_sku("SKU001")
    assert sku["available_stock"] == 90


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "key1")
    result = service.confirm_reservation(res["id"])

    assert result["status"] == "CONFIRMED"
    assert result["order_id"] is not None
    assert result["sku"] == "SKU001"

    order = service.repository.get_orders_paginated(1, 10)
    assert len(order[0]) == 1


def test_confirm_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(999)
    assert exc.value.status_code == 404


def test_confirm_reservation_wrong_status(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "key1")
    service.confirm_reservation(res["id"])

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(res["id"])
    assert exc.value.status_code == 400


def test_confirm_reservation_expired(service, repository):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "key1")

    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    repository._get_connection().cursor().execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, res["id"])
    )
    repository._get_connection().commit()

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(res["id"])
    assert exc.value.status_code == 400
    assert "expired" in str(exc.value.detail).lower()

    reservation = repository.get_reservation(res["id"])
    assert reservation["status"] == "EXPIRED"

    sku = repository.get_sku("SKU001")
    assert sku["available_stock"] == 100


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "key1")

    sku_before = service.repository.get_sku("SKU001")
    assert sku_before["available_stock"] == 90

    result = service.cancel_reservation(res["id"])

    assert result["status"] == "CANCELLED"

    sku_after = service.repository.get_sku("SKU001")
    assert sku_after["available_stock"] == 100


def test_cancel_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.cancel_reservation(999)
    assert exc.value.status_code == 404


def test_cancel_reservation_wrong_status(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "key1")
    service.confirm_reservation(res["id"])

    with pytest.raises(HTTPException) as exc:
        service.cancel_reservation(res["id"])
    assert exc.value.status_code == 400


def test_get_orders_paginated(service):
    service.create_sku("SKU001", 100)
    service.create_sku("SKU002", 100)

    for i in range(15):
        res = service.create_reservation(
            "SKU001" if i % 2 == 0 else "SKU002",
            5,
            f"key_{i}"
        )
        service.confirm_reservation(res["id"])

    page1 = service.get_orders_paginated(1, 10)
    assert page1["total"] == 15
    assert len(page1["orders"]) == 10
    assert page1["page"] == 1

    page2 = service.get_orders_paginated(2, 10)
    assert len(page2["orders"]) == 5
    assert page2["page"] == 2
