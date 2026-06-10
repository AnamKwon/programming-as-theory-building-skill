"""Tests for the service layer."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = str(Path(temp_dir) / "test.db")
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def repo(temp_db):
    """Create a repository instance."""
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    """Create a service instance."""
    return Service(repo)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("SKU-001", 100)

    result = service.adjust_stock("SKU-001", 10)
    assert result["new_stock"] == 110

    result = service.adjust_stock("SKU-001", -20)
    assert result["new_stock"] == 90


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("SKU-001", 100)

    result = service.create_reservation("SKU-001", 50, "idempotency-1")
    assert result.id == 1
    assert result.sku == "SKU-001"
    assert result.quantity == 50
    assert result.status == "PENDING"
    assert result.idempotency_key == "idempotency-1"

    # Verify stock was deducted
    stock = service.repo.get_sku_stock("SKU-001")
    assert stock == 50


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("SKU-001", 30)

    with pytest.raises(Exception) as exc_info:
        service.create_reservation("SKU-001", 50, "idempotency-1")

    assert "Insufficient stock" in str(exc_info.value)


def test_idempotency_key_deduplication(service):
    """Test that same idempotency key returns cached result."""
    service.create_sku("SKU-001", 100)

    # First reservation
    result1 = service.create_reservation("SKU-001", 50, "idempotency-1")
    stock_after_first = service.repo.get_sku_stock("SKU-001")

    # Second reservation with same idempotency key
    result2 = service.create_reservation("SKU-001", 50, "idempotency-1")
    stock_after_second = service.repo.get_sku_stock("SKU-001")

    assert result1.id == result2.id
    assert stock_after_first == stock_after_second == 50  # Stock not deducted twice


def test_confirm_reservation(service):
    """Test reservation confirmation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

    result = service.confirm_reservation(reservation.id)
    assert result["status"] == "CONFIRMED"
    assert "order_id" in result

    # Verify reservation status updated
    updated = service.repo.get_reservation(reservation.id)
    assert updated["status"] == "CONFIRMED"


def test_confirm_non_pending_reservation(service):
    """Test confirming a non-PENDING reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-1")
    service.confirm_reservation(reservation.id)

    # Try to confirm again
    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation.id)

    assert "not in PENDING state" in str(exc_info.value)


def test_confirm_expired_reservation(service, repo):
    """Test confirming an expired reservation."""
    service.create_sku("SKU-001", 100)

    # Create reservation and manually set created_at to 301 seconds ago
    repo.create_reservation("SKU-001", 50, "idempotency-1")
    conn = repo._get_connection()
    cursor = conn.cursor()

    past_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = 1", (past_time,)
    )
    conn.commit()
    conn.close()

    # Manually deduct stock as service.create_reservation would
    repo.adjust_stock("SKU-001", -50)

    # Try to confirm expired reservation
    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(1)

    assert "Reservation expired" in str(exc_info.value)

    # Verify stock was restored
    stock = service.repo.get_sku_stock("SKU-001")
    assert stock == 100


def test_cancel_reservation(service):
    """Test reservation cancellation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

    stock_before = service.repo.get_sku_stock("SKU-001")
    assert stock_before == 50

    result = service.cancel_reservation(reservation.id)
    assert result["status"] == "CANCELLED"
    assert result["stock_restored"] == 50

    # Verify stock was restored
    stock_after = service.repo.get_sku_stock("SKU-001")
    assert stock_after == 100


def test_cancel_non_pending_reservation(service):
    """Test cancelling a non-PENDING reservation."""
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 50, "idempotency-1")
    service.confirm_reservation(reservation.id)

    # Try to cancel confirmed reservation
    with pytest.raises(Exception) as exc_info:
        service.cancel_reservation(reservation.id)

    assert "not in PENDING state" in str(exc_info.value)


def test_get_orders_pagination(service):
    """Test orders pagination."""
    service.create_sku("SKU-001", 500)

    # Create and confirm multiple reservations
    for i in range(25):
        reservation = service.create_reservation(
            "SKU-001", 10, f"idempotency-{i}"
        )
        service.confirm_reservation(reservation.id)

    # Test first page
    result = service.get_orders(page=1, size=10)
    assert len(result["orders"]) == 10
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 25

    # Test second page
    result = service.get_orders(page=2, size=10)
    assert len(result["orders"]) == 10
    assert result["page"] == 2

    # Test third page (partial)
    result = service.get_orders(page=3, size=10)
    assert len(result["orders"]) == 5
    assert result["page"] == 3
