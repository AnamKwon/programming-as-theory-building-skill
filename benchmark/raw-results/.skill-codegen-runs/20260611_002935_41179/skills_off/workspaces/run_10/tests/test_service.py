import pytest
import os
import time
from datetime import datetime, timezone, timedelta

# Change to src directory for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    SKUNotFoundError,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationStatusError,
    ReservationExpiredError,
)


@pytest.fixture(scope="function")
def test_db():
    """Create a test database"""
    db_path = "test_service_commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def repo(test_db):
    """Create a test repository"""
    return Repository(test_db)


@pytest.fixture(scope="function")
def service(repo):
    """Create a test service"""
    return Service(repo)


class TestSKUManagement:
    def test_create_sku(self, service, repo):
        sku_id = service.create_sku("TEST_SKU", 100)
        assert sku_id > 0

        sku_row = repo.get_sku_by_id(sku_id)
        assert sku_row["sku"] == "TEST_SKU"
        assert sku_row["available_stock"] == 100

    def test_adjust_stock_increase(self, service, repo):
        service.create_sku("SKU_ADJUST", 50)

        result = service.adjust_stock("SKU_ADJUST", 25)
        assert result["available_stock"] == 75

    def test_adjust_stock_decrease(self, service, repo):
        service.create_sku("SKU_DECREASE", 100)

        result = service.adjust_stock("SKU_DECREASE", -30)
        assert result["available_stock"] == 70

    def test_adjust_nonexistent_sku(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservationCreation:
    def test_create_reservation(self, service, repo):
        service.create_sku("RES_SKU", 100)

        result = service.create_reservation("RES_SKU", 50, "key1")

        assert result["sku"] == "RES_SKU"
        assert result["quantity"] == 50
        assert result["status"] == "PENDING"
        assert "id" in result
        assert "created_at" in result

    def test_insufficient_stock(self, service):
        service.create_sku("LOW_STOCK", 10)

        with pytest.raises(InsufficientStockError):
            service.create_reservation("LOW_STOCK", 50, "key2")

    def test_reservation_deducts_stock(self, service, repo):
        service.create_sku("STOCK_DEDUCT", 100)
        service.create_reservation("STOCK_DEDUCT", 30, "key3")

        sku_row = repo.get_sku_by_name("STOCK_DEDUCT")
        assert sku_row["available_stock"] == 70

    def test_idempotency_returns_existing(self, service, repo):
        service.create_sku("IDEMPOTENT", 100)

        result1 = service.create_reservation("IDEMPOTENT", 50, "key4")
        result2 = service.create_reservation("IDEMPOTENT", 50, "key4")

        assert result1["id"] == result2["id"]
        assert result1["status"] == result2["status"]

    def test_idempotency_no_double_deduction(self, service, repo):
        service.create_sku("NO_DOUBLE", 100)

        service.create_reservation("NO_DOUBLE", 30, "key5")
        service.create_reservation("NO_DOUBLE", 30, "key5")

        sku_row = repo.get_sku_by_name("NO_DOUBLE")
        assert sku_row["available_stock"] == 70  # Only deducted once


class TestConfirmation:
    def test_confirm_reservation(self, service, repo):
        service.create_sku("CONFIRM_SKU", 100)
        res = service.create_reservation("CONFIRM_SKU", 50, "key6")
        res_id = res["id"]

        result = service.confirm_reservation(res_id)
        assert result["status"] == "confirmed"

        res_row = repo.get_reservation(res_id)
        assert res_row["status"] == "CONFIRMED"

    def test_confirm_creates_order(self, service, repo):
        service.create_sku("ORDER_SKU", 100)
        res = service.create_reservation("ORDER_SKU", 50, "key7")
        res_id = res["id"]

        service.confirm_reservation(res_id)

        # Check that order was created
        orders, _ = repo.get_orders(1, 10)
        assert len(orders) == 1
        assert orders[0]["quantity"] == 50

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_non_pending_reservation(self, service):
        service.create_sku("TWICE_CONFIRM", 100)
        res = service.create_reservation("TWICE_CONFIRM", 50, "key8")
        res_id = res["id"]

        service.confirm_reservation(res_id)

        with pytest.raises(ReservationStatusError):
            service.confirm_reservation(res_id)


class TestExpiration:
    def test_reservation_expired(self, service, repo):
        service.create_sku("EXPIRE_SKU", 100)
        res = service.create_reservation("EXPIRE_SKU", 50, "key9")
        res_id = res["id"]

        # Manually update the reservation created_at to be 301 seconds ago
        import sqlite3
        conn = sqlite3.connect(repo.db_path)
        cursor = conn.cursor()

        past_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (past_time, res_id),
        )
        conn.commit()
        conn.close()

        # Try to confirm - should fail with expired error
        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res_id)

        # Verify reservation status changed to EXPIRED
        res_row = repo.get_reservation(res_id)
        assert res_row["status"] == "EXPIRED"

    def test_expired_restores_stock(self, service, repo):
        service.create_sku("RESTORE_STOCK", 100)
        res = service.create_reservation("RESTORE_STOCK", 50, "key10")
        res_id = res["id"]

        # Make reservation expired
        import sqlite3
        conn = sqlite3.connect(repo.db_path)
        cursor = conn.cursor()
        past_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (past_time, res_id),
        )
        conn.commit()
        conn.close()

        # Try to confirm - should restore stock
        try:
            service.confirm_reservation(res_id)
        except ReservationExpiredError:
            pass

        sku_row = repo.get_sku_by_name("RESTORE_STOCK")
        assert sku_row["available_stock"] == 100  # Stock restored


class TestCancellation:
    def test_cancel_reservation(self, service, repo):
        service.create_sku("CANCEL_SKU", 100)
        res = service.create_reservation("CANCEL_SKU", 50, "key11")
        res_id = res["id"]

        result = service.cancel_reservation(res_id)
        assert result["status"] == "cancelled"

        res_row = repo.get_reservation(res_id)
        assert res_row["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, service, repo):
        service.create_sku("CANCEL_RESTORE", 100)
        res = service.create_reservation("CANCEL_RESTORE", 50, "key12")
        res_id = res["id"]

        service.cancel_reservation(res_id)

        sku_row = repo.get_sku_by_name("CANCEL_RESTORE")
        assert sku_row["available_stock"] == 100

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)

    def test_cancel_non_pending_reservation(self, service):
        service.create_sku("CANCEL_CONFIRMED", 100)
        res = service.create_reservation("CANCEL_CONFIRMED", 50, "key13")
        res_id = res["id"]

        service.confirm_reservation(res_id)

        with pytest.raises(ReservationStatusError):
            service.cancel_reservation(res_id)


class TestOrderRetrieval:
    def test_get_orders_pagination(self, service, repo):
        service.create_sku("MULTI_ORDER", 500)

        # Create multiple orders
        for i in range(15):
            res = service.create_reservation(
                "MULTI_ORDER", 10, f"order_key_{i}"
            )
            service.confirm_reservation(res["id"])

        # First page
        result = service.get_orders(page=1, size=10)
        assert len(result["orders"]) == 10
        assert result["total"] == 15
        assert result["page"] == 1

        # Second page
        result = service.get_orders(page=2, size=10)
        assert len(result["orders"]) == 5
        assert result["total"] == 15
        assert result["page"] == 2

    def test_get_orders_default_pagination(self, service):
        service.create_sku("DEFAULT_PAGE", 200)

        for i in range(5):
            res = service.create_reservation(
                "DEFAULT_PAGE", 10, f"default_key_{i}"
            )
            service.confirm_reservation(res["id"])

        result = service.get_orders()
        assert len(result["orders"]) == 5
        assert result["page"] == 1
        assert result["size"] == 10

    def test_get_empty_orders(self, service):
        result = service.get_orders()
        assert len(result["orders"]) == 0
        assert result["total"] == 0


class TestWorkflow:
    def test_complete_workflow(self, service, repo):
        # Create SKU
        sku_id = service.create_sku("COMPLETE", 100)
        sku_row = repo.get_sku_by_id(sku_id)
        assert sku_row["available_stock"] == 100

        # Create reservation
        res = service.create_reservation("COMPLETE", 50, "complete_key")
        assert res["status"] == "PENDING"
        assert res["quantity"] == 50

        # Check stock was deducted
        sku_row = repo.get_sku_by_name("COMPLETE")
        assert sku_row["available_stock"] == 50

        # Confirm reservation
        service.confirm_reservation(res["id"])

        # Check order exists
        result = service.get_orders(page=1, size=10)
        assert len(result["orders"]) == 1
        assert result["orders"][0]["quantity"] == 50

        # Verify reservation is confirmed
        res_row = repo.get_reservation(res["id"])
        assert res_row["status"] == "CONFIRMED"
