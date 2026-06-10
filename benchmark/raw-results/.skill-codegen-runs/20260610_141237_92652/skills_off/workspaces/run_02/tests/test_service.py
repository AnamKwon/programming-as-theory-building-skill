import pytest
from datetime import datetime, timedelta
import tempfile
from pathlib import Path
from fastapi import HTTPException

from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def repo(temp_db):
    """Create a repository with a temporary database."""
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    """Create a service with the test repository."""
    return CommerceService(repo)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("TEST-SKU-001", 100)
    assert result["sku"] == "TEST-SKU-001"
    assert result["available_stock"] == 100
    assert "id" in result


def test_adjust_stock_increase(service):
    """Test positive stock adjustment."""
    service.create_sku("TEST-SKU-002", 50)
    result = service.adjust_stock("TEST-SKU-002", 25)
    assert result["available_stock"] == 75


def test_adjust_stock_decrease(service):
    """Test negative stock adjustment."""
    service.create_sku("TEST-SKU-003", 100)
    result = service.adjust_stock("TEST-SKU-003", -30)
    assert result["available_stock"] == 70


def test_adjust_stock_nonexistent(service):
    """Test adjusting stock for non-existent SKU."""
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("TEST-SKU-004", 100)
    result = service.create_reservation("TEST-SKU-004", 30, "idempotency-key-1")
    assert result["sku"] == "TEST-SKU-004"
    assert result["quantity"] == 30
    assert result["status"] == "PENDING"
    assert "id" in result


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("TEST-SKU-005", 20)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("TEST-SKU-005", 30, "idempotency-key-2")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_idempotent(service):
    """Test idempotent reservation creation."""
    service.create_sku("TEST-SKU-006", 100)
    result1 = service.create_reservation("TEST-SKU-006", 25, "idempotency-key-3")
    result2 = service.create_reservation("TEST-SKU-006", 25, "idempotency-key-3")

    assert result1["id"] == result2["id"]
    assert result1["sku"] == result2["sku"]
    assert result1["quantity"] == result2["quantity"]

    sku_data = service.repo.get_sku_by_code("TEST-SKU-006")
    assert sku_data["available_stock"] == 75


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    service.create_sku("TEST-SKU-007", 100)
    res = service.create_reservation("TEST-SKU-007", 20, "idempotency-key-4")
    result = service.confirm_reservation(res["id"])

    assert result["status"] == "CONFIRMED"
    assert result["confirmed_at"] is not None

    orders = service.repo.get_orders()
    assert orders["total"] == 1


def test_confirm_reservation_expired(service, repo):
    """Test confirming an expired reservation."""
    service.create_sku("TEST-SKU-008", 100)
    res = service.create_reservation("TEST-SKU-008", 20, "idempotency-key-5")

    repo.update_reservation_status(
        res["id"],
        "PENDING",
        None,
    )

    with repo._get_connection() as conn:
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res["id"]),
        )
        conn.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(res["id"])
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail

    updated = repo.get_reservation(res["id"])
    assert updated["status"] == "EXPIRED"

    sku_data = repo.get_sku_by_code("TEST-SKU-008")
    assert sku_data["available_stock"] == 100


def test_confirm_reservation_not_pending(service):
    """Test confirming a non-pending reservation."""
    service.create_sku("TEST-SKU-009", 100)
    res = service.create_reservation("TEST-SKU-009", 20, "idempotency-key-6")
    service.cancel_reservation(res["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(res["id"])
    assert exc_info.value.status_code == 400
    assert "not in PENDING state" in exc_info.value.detail


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    service.create_sku("TEST-SKU-010", 100)
    res = service.create_reservation("TEST-SKU-010", 20, "idempotency-key-7")
    result = service.cancel_reservation(res["id"])

    assert result["status"] == "CANCELLED"

    sku_data = service.repo.get_sku_by_code("TEST-SKU-010")
    assert sku_data["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    """Test cancelling a non-pending reservation."""
    service.create_sku("TEST-SKU-011", 100)
    res = service.create_reservation("TEST-SKU-011", 20, "idempotency-key-8")
    service.confirm_reservation(res["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(res["id"])
    assert exc_info.value.status_code == 400


def test_get_orders_pagination(service):
    """Test orders pagination."""
    service.create_sku("TEST-SKU-012", 1000)
    for i in range(25):
        res = service.create_reservation("TEST-SKU-012", 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert page1["total"] == 25
    assert page1["page"] == 1
    assert len(page1["items"]) == 10
    assert page1["total_pages"] == 3

    page2 = service.get_orders(page=2, size=10)
    assert page2["page"] == 2
    assert len(page2["items"]) == 10

    page3 = service.get_orders(page=3, size=10)
    assert page3["page"] == 3
    assert len(page3["items"]) == 5


def test_happy_path_workflow(service):
    """Test complete happy path: SKU -> Reserve -> Confirm -> Order."""
    service.create_sku("FINAL-SKU", 50)

    res = service.create_reservation("FINAL-SKU", 15, "final-key")
    assert res["status"] == "PENDING"
    assert res["quantity"] == 15

    confirmed = service.confirm_reservation(res["id"])
    assert confirmed["status"] == "CONFIRMED"

    orders = service.get_orders(page=1, size=10)
    assert orders["total"] == 1
    assert orders["items"][0]["reservation_id"] == res["id"]

    sku_data = service.repo.get_sku_by_code("FINAL-SKU")
    assert sku_data["available_stock"] == 35
