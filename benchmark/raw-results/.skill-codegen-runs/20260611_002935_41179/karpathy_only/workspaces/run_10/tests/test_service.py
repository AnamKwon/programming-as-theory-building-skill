"""Unit tests for the service layer."""

import pytest

from src.commerce_service.models import ReservationStatus
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    return Database(":memory:")


@pytest.fixture
def service(db):
    """Create a service instance."""
    return CommerceService(db)


def test_create_sku(service):
    """Test creating a SKU."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100


def test_adjust_stock(service):
    """Test adjusting stock."""
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", -50)
    assert result["available_stock"] == 50

    result = service.adjust_stock("SKU-001", 25)
    assert result["available_stock"] == 75


def test_create_reservation_happy_path(service):
    """Test creating a reservation with sufficient stock."""
    service.create_sku("SKU-001", 100)
    result = service.create_reservation("SKU-001", 30, "idempotency-1")
    assert result["sku"] == "SKU-001"
    assert result["quantity"] == 30
    assert result["status"] == ReservationStatus.PENDING.value

    # Verify stock was deducted
    sku_data = service.db.get_sku("SKU-001")
    assert sku_data["available_stock"] == 70


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("SKU-001", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 20, "idempotency-1")


def test_create_reservation_idempotency(service):
    """Test idempotent reservation creation."""
    service.create_sku("SKU-001", 100)
    result1 = service.create_reservation("SKU-001", 30, "idempotency-1")
    result2 = service.create_reservation("SKU-001", 30, "idempotency-1")

    assert result1["id"] == result2["id"]
    assert result1["sku"] == result2["sku"]
    assert result1["quantity"] == result2["quantity"]

    # Verify stock was only deducted once
    sku_data = service.db.get_sku("SKU-001")
    assert sku_data["available_stock"] == 70


def test_confirm_reservation_success(service):
    """Test confirming a reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
    result = service.confirm_reservation(reservation["id"])

    assert result["status"] == ReservationStatus.CONFIRMED.value
    assert result["order_id"] is not None


def test_confirm_reservation_invalid_status(service):
    """Test confirming a non-pending reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="not PENDING"):
        service.confirm_reservation(reservation["id"])


def test_cancel_reservation_success(service):
    """Test cancelling a reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
    result = service.cancel_reservation(reservation["id"])

    assert result["status"] == ReservationStatus.CANCELLED.value

    # Verify stock was restored
    sku_data = service.db.get_sku("SKU-001")
    assert sku_data["available_stock"] == 100


def test_cancel_reservation_invalid_status(service):
    """Test cancelling a non-pending reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="not PENDING"):
        service.cancel_reservation(reservation["id"])


def test_get_orders_pagination(service):
    """Test getting orders with pagination."""
    service.create_sku("SKU-001", 100)

    # Create and confirm multiple reservations
    for i in range(15):
        reservation = service.create_reservation(
            "SKU-001", 1, f"idempotency-{i}"
        )
        service.confirm_reservation(reservation["id"])

    # Test first page
    orders, total = service.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 15

    # Test second page
    orders, total = service.get_orders(page=2, size=10)
    assert len(orders) == 5
    assert total == 15
