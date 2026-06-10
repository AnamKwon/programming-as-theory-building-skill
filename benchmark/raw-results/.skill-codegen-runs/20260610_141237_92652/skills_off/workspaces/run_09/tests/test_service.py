import pytest
import sqlite3
import os
from datetime import datetime, timedelta
from commerce_service.service import CommerceService
from commerce_service.repository import init_db, DATABASE_URL


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    yield
    if os.path.exists(DATABASE_URL) and DATABASE_URL != ":memory:":
        os.remove(DATABASE_URL)


@pytest.fixture
def service():
    return CommerceService()


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100
    assert result["total_stock"] == 100


def test_adjust_stock_positive(service):
    service.create_sku("SKU-002", 50)
    result = service.adjust_stock("SKU-002", 30)
    assert result["available_stock"] == 80


def test_adjust_stock_negative(service):
    service.create_sku("SKU-003", 100)
    result = service.adjust_stock("SKU-003", -20)
    assert result["available_stock"] == 80


def test_adjust_stock_nonexistent_sku(service):
    result = service.adjust_stock("NONEXISTENT", 10)
    assert result is None


def test_create_reservation_success(service):
    service.create_sku("SKU-004", 100)
    reservation, error = service.create_reservation("SKU-004", 30, "idempotency-1")
    assert error is None
    assert reservation.sku == "SKU-004"
    assert reservation.quantity == 30
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-005", 50)
    reservation, error = service.create_reservation("SKU-005", 100, "idempotency-2")
    assert error == "Insufficient stock"
    assert reservation is None


def test_create_reservation_nonexistent_sku(service):
    reservation, error = service.create_reservation("NONEXISTENT", 10, "idempotency-3")
    assert error == "SKU not found"
    assert reservation is None


def test_idempotency_key_returns_same_reservation(service):
    service.create_sku("SKU-006", 100)
    reservation1, error1 = service.create_reservation("SKU-006", 20, "idempotency-4")
    assert error1 is None

    reservation2, error2 = service.create_reservation("SKU-006", 20, "idempotency-4")
    assert error2 is None
    assert reservation2.id == reservation1.id
    assert reservation2.quantity == reservation1.quantity


def test_idempotency_does_not_double_deduct(service):
    service.create_sku("SKU-007", 100)
    service.create_reservation("SKU-007", 30, "idempotency-5")
    service.create_reservation("SKU-007", 30, "idempotency-5")

    sku = service.adjust_stock("SKU-007", 0)
    assert sku["available_stock"] == 70


def test_confirm_reservation_success(service):
    service.create_sku("SKU-008", 100)
    reservation, _ = service.create_reservation("SKU-008", 25, "idempotency-6")
    result, error = service.confirm_reservation(reservation.id)
    assert error is None
    assert result["reservation_id"] == reservation.id


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU-009", 100)
    reservation, _ = service.create_reservation("SKU-009", 20, "idempotency-7")
    service.confirm_reservation(reservation.id)
    result, error = service.confirm_reservation(reservation.id)
    assert "not PENDING" in error
    assert result is None


def test_confirm_reservation_nonexistent(service):
    result, error = service.confirm_reservation(999)
    assert error == "Reservation not found"
    assert result is None


def test_expired_reservation_check(service, monkeypatch):
    from unittest.mock import MagicMock, patch
    from datetime import timezone

    service.create_sku("SKU-010", 100)
    reservation, _ = service.create_reservation("SKU-010", 15, "idempotency-8")

    created_at = datetime.fromisoformat(reservation.created_at.replace("Z", "+00:00"))
    mock_now = created_at + timedelta(seconds=301)

    with patch('commerce_service.service.datetime') as mock_datetime:
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.now.return_value = mock_now

        result, error = service.confirm_reservation(reservation.id)
        assert error == "Reservation expired"
        assert result is None


def test_expired_reservation_restores_stock(service):
    from commerce_service.repository import ReservationRepository
    from unittest.mock import patch
    from datetime import timezone

    service.create_sku("SKU-011", 100)
    reservation, _ = service.create_reservation("SKU-011", 20, "idempotency-9")

    with patch('commerce_service.service.datetime') as mock_datetime:
        created_at = datetime.fromisoformat(
            reservation.created_at.replace("Z", "+00:00")
        )
        mock_now = created_at + timedelta(seconds=301)
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.now.return_value = mock_now

        result, error = service.confirm_reservation(reservation.id)
        assert error == "Reservation expired"

        sku = service.adjust_stock("SKU-011", 0)
        assert sku["available_stock"] == 100


def test_cancel_reservation_success(service):
    service.create_sku("SKU-012", 100)
    reservation, _ = service.create_reservation("SKU-012", 25, "idempotency-10")
    result, error = service.cancel_reservation(reservation.id)
    assert error is None
    assert result["status"] == "CANCELLED"

    sku = service.adjust_stock("SKU-012", 0)
    assert sku["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU-013", 100)
    reservation, _ = service.create_reservation("SKU-013", 20, "idempotency-11")
    service.confirm_reservation(reservation.id)
    result, error = service.cancel_reservation(reservation.id)
    assert "not PENDING" in error
    assert result is None


def test_get_orders_paginated(service):
    service.create_sku("SKU-014", 1000)
    for i in range(15):
        reservation, _ = service.create_reservation("SKU-014", 10, f"idempotency-{i}")
        service.confirm_reservation(reservation.id)

    page1 = service.get_orders_paginated(1, 10)
    assert len(page1.items) == 10
    assert page1.total == 15
    assert page1.page == 1
    assert page1.size == 10

    page2 = service.get_orders_paginated(2, 10)
    assert len(page2.items) == 5
    assert page2.total == 15


def test_happy_path_workflow(service):
    service.create_sku("SKU-FINAL", 200)
    reservation, _ = service.create_reservation("SKU-FINAL", 50, "final-reservation")
    assert reservation.status == "PENDING"

    order_result, _ = service.confirm_reservation(reservation.id)
    assert order_result is not None

    orders = service.get_orders_paginated(1, 10)
    assert len(orders.items) == 1
    assert orders.items[0].reservation_id == reservation.id
