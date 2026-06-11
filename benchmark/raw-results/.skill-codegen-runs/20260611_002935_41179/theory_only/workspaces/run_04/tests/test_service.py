"""Tests for the service layer."""

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from commerce_service.repository import init_db
from commerce_service.service import CommerceService


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown for each test."""
    db_path = Path("commerce.db")
    if db_path.exists():
        db_path.unlink()

    init_db()

    yield

    if db_path.exists():
        db_path.unlink()


def test_create_sku():
    """Test creating a SKU."""
    result = CommerceService.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100
    assert "id" in result


def test_create_duplicate_sku():
    """Test creating a duplicate SKU."""
    CommerceService.create_sku("SKU-001", 100)
    with pytest.raises(Exception) as exc_info:
        CommerceService.create_sku("SKU-001", 50)
    assert "already exists" in str(exc_info.value.detail)


def test_adjust_stock():
    """Test adjusting stock."""
    CommerceService.create_sku("SKU-001", 100)
    result = CommerceService.adjust_stock("SKU-001", 50)
    assert result["available_stock"] == 150

    result = CommerceService.adjust_stock("SKU-001", -30)
    assert result["available_stock"] == 120


def test_adjust_stock_nonexistent():
    """Test adjusting stock for nonexistent SKU."""
    with pytest.raises(Exception) as exc_info:
        CommerceService.adjust_stock("SKU-999", 10)
    assert "not found" in str(exc_info.value.detail)


def test_create_reservation_happy_path():
    """Test creating a reservation."""
    CommerceService.create_sku("SKU-001", 100)
    result = CommerceService.create_reservation("SKU-001", 50, "key-1")

    assert result["sku"] == "SKU-001"
    assert result["quantity"] == 50
    assert result["status"] == "PENDING"
    assert isinstance(result["created_at"], datetime)
    assert "id" in result


def test_create_reservation_insufficient_stock():
    """Test creating a reservation with insufficient stock."""
    CommerceService.create_sku("SKU-001", 30)
    with pytest.raises(Exception) as exc_info:
        CommerceService.create_reservation("SKU-001", 50, "key-1")
    assert "Insufficient stock" in str(exc_info.value.detail)


def test_reservation_idempotency():
    """Test that idempotent reservations return the same result."""
    CommerceService.create_sku("SKU-001", 100)

    result1 = CommerceService.create_reservation("SKU-001", 50, "key-1")
    result2 = CommerceService.create_reservation("SKU-001", 50, "key-1")

    assert result1["id"] == result2["id"]
    assert result1["sku"] == result2["sku"]
    assert result1["quantity"] == result2["quantity"]

    # Verify stock was only deducted once
    from commerce_service.repository import SKURepository

    sku_data = SKURepository.get_sku_by_name("SKU-001")
    assert sku_data["available_stock"] == 50  # 100 - 50, not 0


def test_confirm_reservation_happy_path():
    """Test confirming a reservation."""
    CommerceService.create_sku("SKU-001", 100)
    res = CommerceService.create_reservation("SKU-001", 50, "key-1")
    reservation_id = res["id"]

    result = CommerceService.confirm_reservation(reservation_id)
    assert result["status"] == "CONFIRMED"

    from commerce_service.repository import OrderRepository

    orders, _ = OrderRepository.get_orders()
    assert len(orders) == 1
    assert orders[0]["sku"] == "SKU-001"
    assert orders[0]["quantity"] == 50


def test_confirm_reservation_expired():
    """Test confirming an expired reservation."""
    CommerceService.create_sku("SKU-001", 100)
    res = CommerceService.create_reservation("SKU-001", 50, "key-1")
    reservation_id = res["id"]

    # Manipulate the database to set creation time to 301 seconds ago
    from commerce_service.repository import get_db_connection
    from datetime import timedelta

    conn = get_db_connection()
    cursor = conn.cursor()

    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(Exception) as exc_info:
        CommerceService.confirm_reservation(reservation_id)
    assert "Reservation expired" in str(exc_info.value.detail)

    # Verify the reservation status is now EXPIRED
    from commerce_service.repository import ReservationRepository

    updated = ReservationRepository.get_reservation_by_id(reservation_id)
    assert updated["status"] == "EXPIRED"

    # Verify stock was restored
    from commerce_service.repository import SKURepository

    sku_data = SKURepository.get_sku_by_name("SKU-001")
    assert sku_data["available_stock"] == 100


def test_confirm_non_pending_reservation():
    """Test confirming a non-pending reservation."""
    CommerceService.create_sku("SKU-001", 100)
    res = CommerceService.create_reservation("SKU-001", 50, "key-1")
    reservation_id = res["id"]

    CommerceService.confirm_reservation(reservation_id)

    with pytest.raises(Exception) as exc_info:
        CommerceService.confirm_reservation(reservation_id)
    assert "not in PENDING status" in str(exc_info.value.detail)


def test_cancel_reservation():
    """Test cancelling a reservation."""
    CommerceService.create_sku("SKU-001", 100)
    res = CommerceService.create_reservation("SKU-001", 50, "key-1")
    reservation_id = res["id"]

    from commerce_service.repository import SKURepository

    sku_before = SKURepository.get_sku_by_name("SKU-001")
    assert sku_before["available_stock"] == 50

    result = CommerceService.cancel_reservation(reservation_id)
    assert result["status"] == "CANCELLED"

    sku_after = SKURepository.get_sku_by_name("SKU-001")
    assert sku_after["available_stock"] == 100


def test_cancel_non_pending_reservation():
    """Test cancelling a non-pending reservation."""
    CommerceService.create_sku("SKU-001", 100)
    res = CommerceService.create_reservation("SKU-001", 50, "key-1")
    reservation_id = res["id"]

    CommerceService.confirm_reservation(reservation_id)

    with pytest.raises(Exception) as exc_info:
        CommerceService.cancel_reservation(reservation_id)
    assert "not in PENDING status" in str(exc_info.value.detail)


def test_get_orders_pagination():
    """Test getting orders with pagination."""
    CommerceService.create_sku("SKU-001", 1000)

    # Create and confirm 25 reservations
    for i in range(25):
        res = CommerceService.create_reservation("SKU-001", 10, f"key-{i}")
        CommerceService.confirm_reservation(res["id"])

    orders, total = CommerceService.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 25

    orders, total = CommerceService.get_orders(page=2, size=10)
    assert len(orders) == 10
    assert total == 25

    orders, total = CommerceService.get_orders(page=3, size=10)
    assert len(orders) == 5
    assert total == 25


def test_happy_path_workflow():
    """Test the complete happy path workflow."""
    # Create SKU
    sku = CommerceService.create_sku("SKU-HAPPY", 100)
    assert sku["available_stock"] == 100

    # Create reservation
    res = CommerceService.create_reservation("SKU-HAPPY", 30, "key-happy-1")
    assert res["status"] == "PENDING"
    assert res["quantity"] == 30

    # Check stock was deducted
    from commerce_service.repository import SKURepository

    sku_data = SKURepository.get_sku_by_name("SKU-HAPPY")
    assert sku_data["available_stock"] == 70

    # Confirm reservation
    confirmed = CommerceService.confirm_reservation(res["id"])
    assert confirmed["status"] == "CONFIRMED"

    # Check order was created
    orders, total = CommerceService.get_orders()
    assert total == 1
    assert orders[0]["sku"] == "SKU-HAPPY"
    assert orders[0]["quantity"] == 30
