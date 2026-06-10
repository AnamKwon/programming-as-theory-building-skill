import os
import tempfile
import time
from datetime import datetime, timedelta

import pytest

from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
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
    sku_record = service.create_sku("SKU001", 100)
    assert sku_record.sku == "SKU001"
    assert sku_record.available_stock == 100
    assert sku_record.reserved_stock == 0


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)

    new_stock = service.adjust_stock("SKU001", 50)
    assert new_stock == 150

    new_stock = service.adjust_stock("SKU001", -30)
    assert new_stock == 120


def test_adjust_stock_nonexistent_sku(service):
    result = service.adjust_stock("NONEXISTENT", 10)
    assert result is None


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", 100)

    reservation, status = service.create_reservation("SKU001", 50, "idempotency-key-1")
    assert status == "created"
    assert reservation.id is not None
    assert reservation.sku == "SKU001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-key-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 100)

    reservation, status = service.create_reservation("SKU001", 150, "idempotency-key-1")
    assert status == "insufficient_stock"
    assert reservation is None


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)

    res1, status1 = service.create_reservation("SKU001", 50, "idempotency-key-1")
    res2, status2 = service.create_reservation("SKU001", 50, "idempotency-key-1")

    assert status1 == "created"
    assert status2 == "idempotent"
    assert res1.id == res2.id
    assert res1.quantity == res2.quantity


def test_idempotent_reservation_does_not_deduct_stock_twice(service, repository):
    service.create_sku("SKU001", 100)

    res1, _ = service.create_reservation("SKU001", 30, "idempotency-key-1")
    sku_after_first = repository.get_sku("SKU001")
    assert sku_after_first.available_stock == 70
    assert sku_after_first.reserved_stock == 30

    res2, _ = service.create_reservation("SKU001", 30, "idempotency-key-1")
    sku_after_second = repository.get_sku("SKU001")
    assert sku_after_second.available_stock == 70
    assert sku_after_second.reserved_stock == 30


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)

    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-key-1")
    order, error = service.confirm_reservation(reservation.id)

    assert error is None
    assert order.id is not None
    assert order.reservation_id == reservation.id


def test_confirm_reservation_not_found(service):
    order, error = service.confirm_reservation(999)
    assert error == "not_found"
    assert order is None


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)

    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-key-1")
    service.confirm_reservation(reservation.id)

    order, error = service.confirm_reservation(reservation.id)
    assert error == "not_pending"
    assert order is None


def test_reservation_expiration(service, repository):
    service.create_sku("SKU001", 100)

    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-key-1")

    # Manually set created_at to past to simulate expiration
    conn = repository._get_connection()
    cursor = conn.cursor()

    expired_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (expired_time, reservation.id))
    conn.commit()
    conn.close()

    order, error = service.confirm_reservation(reservation.id)
    assert error == "expired"
    assert order is None

    # Verify stock was restored
    sku = repository.get_sku("SKU001")
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_cancel_reservation(service, repository):
    service.create_sku("SKU001", 100)

    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-key-1")

    sku_reserved = repository.get_sku("SKU001")
    assert sku_reserved.available_stock == 50
    assert sku_reserved.reserved_stock == 50

    success, error = service.cancel_reservation(reservation.id)
    assert success is True
    assert error is None

    sku_restored = repository.get_sku("SKU001")
    assert sku_restored.available_stock == 100
    assert sku_restored.reserved_stock == 0


def test_cancel_reservation_not_found(service):
    success, error = service.cancel_reservation(999)
    assert success is False
    assert error == "not_found"


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)

    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-key-1")
    service.confirm_reservation(reservation.id)

    success, error = service.cancel_reservation(reservation.id)
    assert success is False
    assert error == "not_pending"


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    # Create multiple orders
    for i in range(25):
        res, _ = service.create_reservation("SKU001", 10, f"key-{i}")
        service.confirm_reservation(res.id)

    orders_page1, total1 = service.get_orders(page=1, size=10)
    assert len(orders_page1) == 10
    assert total1 == 25

    orders_page2, total2 = service.get_orders(page=2, size=10)
    assert len(orders_page2) == 10
    assert total2 == 25

    orders_page3, total3 = service.get_orders(page=3, size=10)
    assert len(orders_page3) == 5
    assert total3 == 25
