import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def repo(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert result["created_at"]


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 10)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 110

    result = service.adjust_stock("SKU001", -20)
    assert result["available_stock"] == 90


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", 100)
    reservation, status_code = service.create_reservation("SKU001", 10, "idempotency-1")

    assert status_code == 201
    assert reservation["id"]
    assert reservation["sku"] == "SKU001"
    assert reservation["quantity"] == 10
    assert reservation["status"] == "PENDING"
    assert reservation["idempotency_key"] == "idempotency-1"

    # Verify stock was deducted
    sku = service.repo.get_sku("SKU001")
    assert sku["available_stock"] == 90


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 5)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 10, "idempotency-1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)

    reservation1, status1 = service.create_reservation("SKU001", 10, "idempotency-1")

    # Second call with same idempotency key should return cached result
    reservation2, status2 = service.create_reservation("SKU001", 10, "idempotency-1")

    assert status2 == 200
    assert reservation1["id"] == reservation2["id"]

    # Verify stock was only deducted once
    sku = service.repo.get_sku("SKU001")
    assert sku["available_stock"] == 90


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 10, "idempotency-1")

    confirmed = service.confirm_reservation(reservation["id"])
    assert confirmed["status"] == "CONFIRMED"

    # Verify order was created
    orders, _ = service.get_orders(page=1, size=10)
    assert len(orders) == 1
    assert orders[0]["sku"] == "SKU001"
    assert orders[0]["quantity"] == 10


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 10, "idempotency-1")

    # Confirm once
    service.confirm_reservation(reservation["id"])

    # Try to confirm again
    with pytest.raises(ValueError, match="PENDING"):
        service.confirm_reservation(reservation["id"])


def test_confirm_reservation_expired(service):
    service.create_sku("SKU001", 100)

    # Create a reservation
    reservation, _ = service.create_reservation("SKU001", 10, "idempotency-1")
    reservation_id = reservation["id"]

    # Manually set created_at to be old
    conn = service.repo._get_connection()
    cursor = conn.cursor()
    from datetime import timezone
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    # Try to confirm
    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation_id)

    # Verify status is EXPIRED
    expired_res = service.repo.get_reservation(reservation_id)
    assert expired_res["status"] == "EXPIRED"

    # Verify stock was restored
    sku = service.repo.get_sku("SKU001")
    assert sku["available_stock"] == 100


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 10, "idempotency-1")

    cancelled = service.cancel_reservation(reservation["id"])
    assert cancelled["status"] == "CANCELLED"

    # Verify stock was restored
    sku = service.repo.get_sku("SKU001")
    assert sku["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 10, "idempotency-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="PENDING"):
        service.cancel_reservation(reservation["id"])


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 100)

    # Create and confirm 15 reservations
    for i in range(15):
        reservation, _ = service.create_reservation("SKU001", 5, f"idempotency-{i}")
        service.confirm_reservation(reservation["id"])

    # Get first page
    orders, total = service.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 15

    # Get second page
    orders, total = service.get_orders(page=2, size=10)
    assert len(orders) == 5
    assert total == 15

    # Different page size
    orders, total = service.get_orders(page=1, size=5)
    assert len(orders) == 5
    assert total == 15
