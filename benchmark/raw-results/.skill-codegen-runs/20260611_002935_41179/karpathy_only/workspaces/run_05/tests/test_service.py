"""Tests for the service layer."""

import os
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.commerce_service.repository import Repository, get_db_connection, init_db, DATABASE_PATH
from src.commerce_service.service import CommerceService


@pytest.fixture(autouse=True)
def clean_db():
    """Clean up database before each test."""
    db_path = Path(str(DATABASE_PATH))
    if db_path.exists():
        db_path.unlink()
    init_db()
    yield
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def repository():
    """Provide a repository instance."""
    return Repository()


@pytest.fixture
def service(repository):
    """Provide a service instance."""
    return CommerceService(repository)


def test_create_sku_happy_path(service):
    """Test creating a SKU."""
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100


def test_adjust_stock_positive(service):
    """Test adjusting stock by positive amount."""
    service.create_sku("SKU001", 50)
    result = service.adjust_stock("SKU001", 25)
    assert result.available_stock == 75


def test_adjust_stock_negative(service):
    """Test adjusting stock by negative amount."""
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -30)
    assert result.available_stock == 70


def test_adjust_stock_nonexistent_sku(service):
    """Test adjusting stock for non-existent SKU."""
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_happy_path(service):
    """Test creating a reservation."""
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-key-1")
    assert result.id is not None
    assert result.sku == "SKU001"
    assert result.quantity == 10
    assert result.status == "PENDING"
    assert result.idempotency_key == "idempotency-key-1"


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails when insufficient stock."""
    service.create_sku("SKU001", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 100, "idempotency-key-1")


def test_create_reservation_deducts_stock(service):
    """Test that creating a reservation deducts stock."""
    service.create_sku("SKU001", 100)
    service.create_reservation("SKU001", 30, "idempotency-key-1")

    sku_data = service.repo.get_sku_by_name("SKU001")
    assert sku_data["available_stock"] == 70


def test_idempotent_reservation_retry(service):
    """Test idempotency - same key returns same reservation without deducting again."""
    service.create_sku("SKU001", 100)

    result1 = service.create_reservation("SKU001", 20, "idempotency-key-1")
    stock_after_first = service.repo.get_sku_by_name("SKU001")["available_stock"]

    result2 = service.create_reservation("SKU001", 20, "idempotency-key-1")
    stock_after_second = service.repo.get_sku_by_name("SKU001")["available_stock"]

    assert result1.id == result2.id
    assert result1.idempotency_key == result2.idempotency_key
    assert stock_after_first == stock_after_second == 80


def test_confirm_reservation_happy_path(service):
    """Test confirming a reservation."""
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
    confirmed = service.confirm_reservation(reservation.id)

    assert confirmed.status == "CONFIRMED"
    assert confirmed.confirmed_at is not None


def test_confirm_reservation_creates_order(service):
    """Test that confirming a reservation creates an order."""
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
    service.confirm_reservation(reservation.id)

    orders, total = service.repo.get_orders(1, 10)
    assert total == 1
    assert orders[0]["sku"] == "SKU001"
    assert orders[0]["quantity"] == 10


def test_confirm_non_pending_reservation(service):
    """Test confirming a reservation that is not PENDING fails."""
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(reservation.id)


def test_reservation_expiration(service):
    """Test that expired reservations cannot be confirmed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"

        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
            cursor.execute(
                "UPDATE reservation SET created_at = ? WHERE id = ?",
                (old_time, reservation.id),
            )
            conn.commit()

        stock_before = service.repo.get_sku_by_name("SKU001")["available_stock"]

        with pytest.raises(ValueError, match="Reservation expired"):
            service.confirm_reservation(reservation.id)

        stock_after = service.repo.get_sku_by_name("SKU001")["available_stock"]
        assert stock_after == 100

        updated_reservation = service.repo.get_reservation(reservation.id)
        assert updated_reservation["status"] == "EXPIRED"


def test_cancel_reservation_happy_path(service):
    """Test cancelling a reservation."""
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
    stock_after_reserve = service.repo.get_sku_by_name("SKU001")["available_stock"]

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled["status"] == "CANCELLED"

    stock_after_cancel = service.repo.get_sku_by_name("SKU001")["available_stock"]
    assert stock_after_cancel == 100


def test_cancel_non_pending_reservation(service):
    """Test cancelling a non-PENDING reservation fails."""
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "idempotency-key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.cancel_reservation(reservation.id)


def test_pagination_default(service):
    """Test pagination with default parameters."""
    service.create_sku("SKU001", 100)
    for i in range(15):
        reservation = service.create_reservation("SKU001", 5, f"key-{i}")
        service.confirm_reservation(reservation.id)

    result = service.get_orders(1, 10)
    assert result.page == 1
    assert result.size == 10
    assert result.total == 15
    assert len(result.items) == 10


def test_pagination_offset(service):
    """Test pagination offset behavior."""
    service.create_sku("SKU001", 100)
    for i in range(15):
        reservation = service.create_reservation("SKU001", 5, f"key-{i}")
        service.confirm_reservation(reservation.id)

    page1 = service.get_orders(1, 5)
    page2 = service.get_orders(2, 5)
    page3 = service.get_orders(3, 5)

    assert len(page1.items) == 5
    assert len(page2.items) == 5
    assert len(page3.items) == 5
    assert page1.total == 15
    assert page2.total == 15
    assert page3.total == 15
