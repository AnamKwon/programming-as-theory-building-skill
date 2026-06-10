"""Tests for the service layer."""

import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repo(temp_db):
    """Create a repository with a temporary database."""
    return Repository(db_file=temp_db)


@pytest.fixture
def service(repo):
    """Create a service with the test repository."""
    return CommerceService(repo)


def test_create_sku(service):
    """Test creating a new SKU."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100


def test_adjust_stock(service):
    """Test adjusting stock levels."""
    service.create_sku("SKU-002", 50)
    result = service.adjust_stock("SKU-002", 25)
    assert result["available_stock"] == 75

    result = service.adjust_stock("SKU-002", -10)
    assert result["available_stock"] == 65


def test_create_reservation_happy_path(service):
    """Test the happy path: create SKU, reserve stock."""
    service.create_sku("SKU-003", 100)
    result, status_code = service.create_reservation("SKU-003", 30, "idem-key-1")
    assert status_code == 201
    assert result["sku"] == "SKU-003"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails with insufficient stock."""
    service.create_sku("SKU-004", 50)
    result, status_code = service.create_reservation("SKU-004", 100, "idem-key-2")
    assert status_code == 400
    assert result["detail"] == "Insufficient stock"


def test_idempotent_reservation(service):
    """Test that idempotent requests return the same response without double-deduction."""
    service.create_sku("SKU-005", 100)

    # First request
    result1, status_code1 = service.create_reservation("SKU-005", 30, "idem-key-3")
    assert status_code1 == 201
    assert result1["id"] == 1

    # Check stock was deducted
    sku = service.repo.get_sku("SKU-005")
    assert sku["available_stock"] == 70

    # Second request with same idempotency key
    result2, status_code2 = service.create_reservation("SKU-005", 30, "idem-key-3")
    assert status_code2 == 201
    assert result2["id"] == 1
    assert result2 == result1

    # Check stock wasn't deducted again
    sku = service.repo.get_sku("SKU-005")
    assert sku["available_stock"] == 70


def test_confirm_reservation(service):
    """Test confirming a reservation creates an order."""
    service.create_sku("SKU-006", 100)
    res_result, _ = service.create_reservation("SKU-006", 25, "idem-key-4")
    reservation_id = res_result["id"]

    conf_result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 200
    assert conf_result["status"] == "CONFIRMED"

    # Verify order was created
    order = service.repo.get_order_by_id(1)
    assert order is not None
    assert order["reservation_id"] == reservation_id


def test_cancel_reservation_restores_stock(service):
    """Test canceling a reservation restores stock."""
    service.create_sku("SKU-007", 100)
    res_result, _ = service.create_reservation("SKU-007", 40, "idem-key-5")
    reservation_id = res_result["id"]

    # Check stock was deducted
    sku = service.repo.get_sku("SKU-007")
    assert sku["available_stock"] == 60

    # Cancel reservation
    cancel_result, status_code = service.cancel_reservation(reservation_id)
    assert status_code == 200
    assert cancel_result["status"] == "CANCELLED"

    # Check stock was restored
    sku = service.repo.get_sku("SKU-007")
    assert sku["available_stock"] == 100


def test_confirm_non_pending_reservation_fails(service):
    """Test confirming a non-PENDING reservation fails."""
    service.create_sku("SKU-008", 100)
    res_result, _ = service.create_reservation("SKU-008", 20, "idem-key-6")
    reservation_id = res_result["id"]

    # Confirm once
    service.confirm_reservation(reservation_id)

    # Try to confirm again
    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 400
    assert result["detail"] == "Reservation is not in PENDING status"


def test_expired_reservation(service):
    """Test that expired reservations cannot be confirmed."""
    service.create_sku("SKU-009", 100)

    # Create a reservation and manually set its created_at to > 300 seconds ago
    repo = service.repo
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    repo.create_reservation("SKU-009", 30, "idem-key-7", old_time)
    repo.deduct_stock("SKU-009", 30)

    # Try to confirm - should fail
    result, status_code = service.confirm_reservation(1)
    assert status_code == 400
    assert result["detail"] == "Reservation expired"

    # Verify status was set to EXPIRED
    reservation = repo.get_reservation(1)
    assert reservation["status"] == "EXPIRED"

    # Verify stock was restored
    sku = repo.get_sku("SKU-009")
    assert sku["available_stock"] == 100


def test_cancel_non_pending_reservation_fails(service):
    """Test canceling a non-PENDING reservation fails."""
    service.create_sku("SKU-010", 100)
    res_result, _ = service.create_reservation("SKU-010", 20, "idem-key-8")
    reservation_id = res_result["id"]

    # Confirm the reservation
    service.confirm_reservation(reservation_id)

    # Try to cancel
    result, status_code = service.cancel_reservation(reservation_id)
    assert status_code == 400
    assert result["detail"] == "Reservation is not in PENDING status"


def test_get_orders_pagination(service):
    """Test pagination on orders listing."""
    service.create_sku("SKU-011", 1000)

    # Create and confirm multiple reservations
    for i in range(25):
        res_result, _ = service.create_reservation("SKU-011", 10, f"idem-key-pagination-{i}")
        service.confirm_reservation(res_result["id"])

    # Get first page
    result1 = service.get_orders(page=1, size=10)
    assert result1["page"] == 1
    assert result1["size"] == 10
    assert result1["total"] == 25
    assert len(result1["orders"]) == 10

    # Get second page
    result2 = service.get_orders(page=2, size=10)
    assert result2["page"] == 2
    assert len(result2["orders"]) == 10

    # Get third page (should have 5 items)
    result3 = service.get_orders(page=3, size=10)
    assert result3["page"] == 3
    assert len(result3["orders"]) == 5
