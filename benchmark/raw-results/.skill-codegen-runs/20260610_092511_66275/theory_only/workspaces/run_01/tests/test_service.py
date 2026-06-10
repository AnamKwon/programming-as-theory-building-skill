"""Tests for the service business logic layer."""
import pytest
from datetime import datetime, timedelta
import tempfile
import os

from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(f"sqlite:///{path}")
    yield db
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def service(temp_db):
    """Create a service instance with temp database."""
    return CommerceService(temp_db)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("SKU-001", "Widget")
    assert result["id"] == "SKU-001"
    assert result["name"] == "Widget"
    assert "created_at" in result


def test_adjust_stock_creates_if_not_exist(service):
    """Test that adjusting stock creates it if it doesn't exist."""
    service.create_sku("SKU-001", "Widget")
    result = service.adjust_stock("SKU-001", 100)
    assert result["sku_id"] == "SKU-001"
    assert result["quantity"] == 100
    assert result["reserved"] == 0
    assert result["available"] == 100


def test_adjust_stock_not_found(service):
    """Test adjusting stock for non-existent SKU."""
    result = service.adjust_stock("NONEXISTENT", 100)
    assert result is None


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 100)

    result = service.create_reservation("SKU-001", 50)
    assert result["sku_id"] == "SKU-001"
    assert result["quantity"] == 50
    assert result["status"] == "pending"
    assert "id" in result
    assert "expires_at" in result


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails with insufficient stock."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 30)

    result = service.create_reservation("SKU-001", 50)
    assert result is None


def test_create_reservation_idempotent(service):
    """Test idempotent reservation creation."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 100)

    result1 = service.create_reservation("SKU-001", 50, idempotency_key="key-1")
    assert result1["id"]
    reservation_id_1 = result1["id"]

    result2 = service.create_reservation("SKU-001", 50, idempotency_key="key-1")
    assert result2["id"] == reservation_id_1
    assert result2.get("is_duplicate") is True


def test_confirm_reservation_creates_order(service):
    """Test that confirming a reservation creates an order."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 50)
    reservation_id = reservation["id"]

    result = service.confirm_reservation(reservation_id)
    assert result["order_id"]
    assert result["sku_id"] == "SKU-001"
    assert result["quantity"] == 50
    assert result["status"] == "confirmed"


def test_confirm_reservation_not_found(service):
    """Test confirming non-existent reservation."""
    result = service.confirm_reservation("NONEXISTENT")
    assert result is None


def test_cancel_reservation_success(service):
    """Test cancelling a pending reservation."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 100)

    reservation = service.create_reservation("SKU-001", 50)
    reservation_id = reservation["id"]

    success = service.cancel_reservation(reservation_id)
    assert success is True


def test_cancel_reservation_not_found(service):
    """Test cancelling non-existent reservation."""
    success = service.cancel_reservation("NONEXISTENT")
    assert success is False


def test_list_orders_pagination(service):
    """Test order listing with pagination."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 1000)

    # Create 5 orders
    for i in range(5):
        reservation = service.create_reservation("SKU-001", 10)
        service.confirm_reservation(reservation["id"])

    # Test first page
    result = service.list_orders(offset=0, limit=2)
    assert len(result["items"]) == 2
    assert result["total"] == 5
    assert result["offset"] == 0
    assert result["limit"] == 2

    # Test second page
    result = service.list_orders(offset=2, limit=2)
    assert len(result["items"]) == 2

    # Test beyond available items
    result = service.list_orders(offset=10, limit=10)
    assert len(result["items"]) == 0


def test_cleanup_expired_reservations(service):
    """Test cleanup of expired reservations."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 100)

    # Create reservation with short TTL
    reservation = service.create_reservation("SKU-001", 50, ttl_seconds=1)

    # Simulate expiration by modifying the database directly
    session = service.db.get_session()
    from commerce_service.models import ReservationModel
    from datetime import datetime
    reservation_record = session.query(ReservationModel).filter(
        ReservationModel.id == reservation["id"]
    ).first()
    reservation_record.expires_at = datetime.utcnow() - timedelta(seconds=10)
    session.commit()
    session.close()

    # Cleanup should find and mark as expired
    expired_count = service.cleanup_expired_reservations()
    assert expired_count == 1


def test_stock_reservation_tracking(service):
    """Test that reserved stock is properly tracked."""
    service.create_sku("SKU-001", "Widget")
    service.adjust_stock("SKU-001", 100)

    # Create first reservation
    res1 = service.create_reservation("SKU-001", 30)

    # Create second reservation - should still succeed
    res2 = service.create_reservation("SKU-001", 40)
    assert res2 is not None

    # Third reservation should fail (only 30 available)
    res3 = service.create_reservation("SKU-001", 40)
    assert res3 is None

    # Cancel first reservation
    service.cancel_reservation(res1["id"])

    # Now third reservation should succeed
    res3 = service.create_reservation("SKU-001", 40)
    assert res3 is not None
