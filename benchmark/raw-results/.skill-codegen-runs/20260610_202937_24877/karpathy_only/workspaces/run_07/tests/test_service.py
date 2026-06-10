"""Service layer tests."""
import pytest
import time
from datetime import datetime
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create in-memory database for testing."""
    return Database(":memory:")


@pytest.fixture
def service(db):
    """Create service instance."""
    return CommerceService(db)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["initial_stock"] == 100


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("SKU-002", 50)
    result = service.adjust_stock("SKU-002", 10)
    assert result["new_stock"] == 60

    result = service.adjust_stock("SKU-002", -15)
    assert result["new_stock"] == 45


def test_create_reservation_success(service):
    """Test happy path: reservation creation."""
    service.create_sku("SKU-003", 100)
    result, status_code = service.create_reservation(
        "SKU-003", 30, "idempotency-key-1"
    )
    assert status_code == 201
    assert result["sku"] == "SKU-003"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"
    assert result["idempotency_key"] == "idempotency-key-1"
    assert isinstance(result["created_at"], datetime)


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("SKU-004", 20)
    result, status_code = service.create_reservation(
        "SKU-004", 50, "idempotency-key-2"
    )
    assert status_code == 400
    assert "Insufficient stock" in result["detail"]


def test_create_reservation_idempotency(service):
    """Test idempotent reservation creation."""
    service.create_sku("SKU-005", 100)
    result1, status1 = service.create_reservation(
        "SKU-005", 25, "idempotency-key-3"
    )
    assert status1 == 201

    result2, status2 = service.create_reservation(
        "SKU-005", 25, "idempotency-key-3"
    )
    assert status2 == 200
    assert result1["id"] == result2["id"]
    assert result1["quantity"] == result2["quantity"]
    assert result1["idempotency_key"] == result2["idempotency_key"]

    available = service.db.get_sku_stock("SKU-005")
    assert available == 75


def test_confirm_reservation_success(service):
    """Test happy path: confirm reservation."""
    service.create_sku("SKU-006", 100)
    res, _ = service.create_reservation("SKU-006", 40, "idempotency-key-4")
    reservation_id = res["id"]

    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 200
    assert result["sku"] == "SKU-006"
    assert result["quantity"] == 40


def test_confirm_reservation_not_pending(service):
    """Test confirming a non-PENDING reservation."""
    service.create_sku("SKU-007", 100)
    res, _ = service.create_reservation("SKU-007", 20, "idempotency-key-5")
    reservation_id = res["id"]

    service.confirm_reservation(reservation_id)

    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 400
    assert "not in PENDING status" in result["detail"]


def test_confirm_reservation_expired(service):
    """Test confirming an expired reservation."""
    service.create_sku("SKU-008", 100)
    res, _ = service.create_reservation("SKU-008", 35, "idempotency-key-6")
    reservation_id = res["id"]

    time.sleep(301)

    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 400
    assert "expired" in result["detail"]

    reservation = service.db.get_reservation(reservation_id)
    assert reservation["status"] == "EXPIRED"

    available = service.db.get_sku_stock("SKU-008")
    assert available == 100


def test_cancel_reservation(service):
    """Test reservation cancellation."""
    service.create_sku("SKU-009", 100)
    res, _ = service.create_reservation("SKU-009", 50, "idempotency-key-7")
    reservation_id = res["id"]

    available_before = service.db.get_sku_stock("SKU-009")
    assert available_before == 50

    result, status_code = service.cancel_reservation(reservation_id)
    assert status_code == 200
    assert result["status"] == "CANCELLED"

    available_after = service.db.get_sku_stock("SKU-009")
    assert available_after == 100


def test_cancel_reservation_not_pending(service):
    """Test cancelling a non-PENDING reservation."""
    service.create_sku("SKU-010", 100)
    res, _ = service.create_reservation("SKU-010", 25, "idempotency-key-8")
    reservation_id = res["id"]

    service.confirm_reservation(reservation_id)

    result, status_code = service.cancel_reservation(reservation_id)
    assert status_code == 400
    assert "not in PENDING status" in result["detail"]


def test_get_orders_pagination(service):
    """Test orders pagination."""
    service.create_sku("SKU-011", 1000)

    for i in range(25):
        res, _ = service.create_reservation("SKU-011", 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    result = service.get_orders(page=1, size=10)
    assert len(result["orders"]) == 10
    assert result["total"] == 25
    assert result["page"] == 1
    assert result["size"] == 10

    result = service.get_orders(page=2, size=10)
    assert len(result["orders"]) == 10

    result = service.get_orders(page=3, size=10)
    assert len(result["orders"]) == 5
