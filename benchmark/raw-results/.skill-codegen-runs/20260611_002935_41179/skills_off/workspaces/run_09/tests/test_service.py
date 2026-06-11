"""Tests for the service layer."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from commerce_service.repository import Repository, init_db, DATABASE_PATH, get_connection
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidReservationStatusError,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Set up test database for each test."""
    if Path(DATABASE_PATH).exists():
        os.remove(DATABASE_PATH)
    init_db()
    yield
    if Path(DATABASE_PATH).exists():
        os.remove(DATABASE_PATH)


@pytest.fixture
def repo():
    """Create a repository instance."""
    return Repository()


@pytest.fixture
def service(repo):
    """Create a service instance."""
    return CommerceService(repo)


def test_create_sku(service):
    """Test creating a SKU."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["stock"] == 100


def test_adjust_stock(service):
    """Test adjusting stock."""
    service.create_sku("SKU-002", 50)
    result = service.adjust_stock("SKU-002", 25)
    assert result["stock"] == 75

    result = service.adjust_stock("SKU-002", -10)
    assert result["stock"] == 65


def test_reserve_stock_success(service):
    """Test successful stock reservation."""
    service.create_sku("SKU-003", 100)
    result = service.reserve_stock("SKU-003", 30, "idempotent-key-1")
    assert result["id"] == 1
    assert result["sku"] == "SKU-003"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"


def test_reserve_stock_insufficient(service):
    """Test reservation with insufficient stock."""
    service.create_sku("SKU-004", 10)
    with pytest.raises(InsufficientStockError):
        service.reserve_stock("SKU-004", 20, "idempotent-key-2")


def test_reserve_stock_idempotency(service):
    """Test that idempotency prevents duplicate reservations."""
    service.create_sku("SKU-005", 100)
    result1 = service.reserve_stock("SKU-005", 30, "idempotent-key-3")
    result2 = service.reserve_stock("SKU-005", 30, "idempotent-key-3")

    assert result1["id"] == result2["id"]
    assert result1["created_at"] == result2["created_at"]

    sku_data = service.repo.get_sku("SKU-005")
    assert sku_data["stock"] == 70


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    service.create_sku("SKU-006", 100)
    reservation = service.reserve_stock("SKU-006", 25, "idempotent-key-4")

    result = service.confirm_reservation(reservation["id"])
    assert result["reservation_id"] == reservation["id"]
    assert result["status"] == "CONFIRMED"
    assert result["order_id"] is not None


def test_confirm_reservation_expired(service):
    """Test confirmation of expired reservation."""
    service.create_sku("SKU-007", 100)
    reservation = service.reserve_stock("SKU-007", 30, "idempotent-key-5")
    reservation_id = reservation["id"]

    old_timestamp = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_timestamp, reservation_id),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation_id)

    updated = service.repo.get_reservation(reservation_id)
    assert updated["status"] == "EXPIRED"

    sku_data = service.repo.get_sku("SKU-007")
    assert sku_data["stock"] == 100


def test_confirm_reservation_non_pending(service):
    """Test confirming a non-PENDING reservation."""
    service.create_sku("SKU-008", 100)
    reservation = service.reserve_stock("SKU-008", 20, "idempotent-key-6")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(InvalidReservationStatusError):
        service.confirm_reservation(reservation["id"])


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    service.create_sku("SKU-009", 100)
    reservation = service.reserve_stock("SKU-009", 35, "idempotent-key-7")

    result = service.cancel_reservation(reservation["id"])
    assert result["reservation_id"] == reservation["id"]
    assert result["status"] == "CANCELLED"
    assert result["stock_restored"] == 35

    sku_data = service.repo.get_sku("SKU-009")
    assert sku_data["stock"] == 100


def test_cancel_reservation_non_pending(service):
    """Test cancelling a non-PENDING reservation."""
    service.create_sku("SKU-010", 100)
    reservation = service.reserve_stock("SKU-010", 25, "idempotent-key-8")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(InvalidReservationStatusError):
        service.cancel_reservation(reservation["id"])


def test_get_orders_pagination(service):
    """Test pagination of orders."""
    service.create_sku("SKU-011", 1000)

    for i in range(25):
        res = service.reserve_stock("SKU-011", 10, f"idempotent-key-{i+100}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert len(page1["orders"]) == 10
    assert page1["page"] == 1
    assert page1["total"] == 25

    page2 = service.get_orders(page=2, size=10)
    assert len(page2["orders"]) == 10
    assert page2["page"] == 2

    page3 = service.get_orders(page=3, size=10)
    assert len(page3["orders"]) == 5
    assert page3["page"] == 3
