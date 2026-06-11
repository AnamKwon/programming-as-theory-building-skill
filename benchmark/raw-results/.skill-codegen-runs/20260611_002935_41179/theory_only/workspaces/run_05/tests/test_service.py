import pytest
import tempfile
import os
from datetime import datetime, timezone
from time import sleep
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def repo(temp_db):
    """Create a repository with a temporary database"""
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    """Create a service with the repository"""
    return CommerceService(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        """Test creating a new SKU"""
        result = service.create_sku("SKU001", 100)
        assert result["sku"] == "SKU001"
        assert result["available_stock"] == 100
        assert "id" in result
        assert "created_at" in result

    def test_get_sku(self, service):
        """Test retrieving a SKU"""
        service.create_sku("SKU001", 50)
        result = service.get_sku("SKU001")
        assert result["sku"] == "SKU001"
        assert result["available_stock"] == 50

    def test_get_nonexistent_sku(self, service):
        """Test retrieving a non-existent SKU"""
        result = service.get_sku("NONEXISTENT")
        assert result is None


class TestStockAdjustment:
    def test_adjust_stock_increase(self, service):
        """Test increasing stock"""
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["available_stock"] == 150

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock"""
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["available_stock"] == 70

    def test_adjust_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU"""
        result = service.adjust_stock("NONEXISTENT", 10)
        assert result is None


class TestReservations:
    def test_create_reservation_success(self, service):
        """Test creating a reservation with sufficient stock"""
        service.create_sku("SKU001", 100)
        result = service.create_reservation("SKU001", 30, "key123")
        assert result["id"] is not None
        assert result["sku"] == "SKU001"
        assert result["quantity"] == 30
        assert result["status"] == "PENDING"
        assert result["idempotency_key"] == "key123"

    def test_create_reservation_deducts_stock(self, service):
        """Test that creating a reservation deducts stock"""
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "key123")
        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 70

    def test_create_reservation_insufficient_stock(self, service):
        """Test that reservation fails with insufficient stock"""
        service.create_sku("SKU001", 20)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU001", 30, "key123")

    def test_reservation_idempotency(self, service):
        """Test that duplicate idempotency keys return same reservation"""
        service.create_sku("SKU001", 100)
        result1 = service.create_reservation("SKU001", 30, "key123")
        result2 = service.create_reservation("SKU001", 50, "key123")
        assert result1["id"] == result2["id"]
        assert result2["quantity"] == 30  # Original quantity, not 50

    def test_reservation_idempotency_no_double_deduction(self, service):
        """Test that idempotent retry doesn't deduct stock twice"""
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "key123")
        service.create_reservation("SKU001", 30, "key123")
        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 70  # Deducted only once

    def test_create_reservation_nonexistent_sku(self, service):
        """Test reservation for non-existent SKU"""
        result = service.create_reservation("NONEXISTENT", 10, "key123")
        assert result is None


class TestConfirmation:
    def test_confirm_reservation_success(self, service):
        """Test confirming a valid reservation"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        result = service.confirm_reservation(res["id"])
        assert result["status"] == "CONFIRMED"

    def test_confirm_creates_order(self, service):
        """Test that confirming creates an order"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        service.confirm_reservation(res["id"])
        orders = service.get_orders_paginated(1, 10)
        assert len(orders["items"]) == 1
        assert orders["items"][0]["reservation_id"] == res["id"]

    def test_confirm_nonpending_fails(self, service):
        """Test that confirming non-PENDING reservation fails"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        service.confirm_reservation(res["id"])
        with pytest.raises(ValueError, match="not in PENDING status"):
            service.confirm_reservation(res["id"])

    def test_confirm_nonexistent_fails(self, service):
        """Test that confirming non-existent reservation returns None"""
        result = service.confirm_reservation(9999)
        assert result is None

    def test_confirm_expired_reservation(self, service):
        """Test that confirming expired reservation fails"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        sleep(1)  # Short sleep to ensure some time passes
        # Manually set created_at to be > 300 seconds old
        import sqlite3
        conn = sqlite3.connect(service.repo.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = datetime('now', '-301 seconds') WHERE id = ?",
            (res["id"],)
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res["id"])

    def test_confirm_expired_restores_stock(self, service):
        """Test that confirming expired reservation restores stock"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        # Set created_at to be expired
        import sqlite3
        conn = sqlite3.connect(service.repo.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = datetime('now', '-301 seconds') WHERE id = ?",
            (res["id"],)
        )
        conn.commit()
        conn.close()

        try:
            service.confirm_reservation(res["id"])
        except ValueError:
            pass

        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 100  # Stock restored


class TestCancellation:
    def test_cancel_reservation_success(self, service):
        """Test cancelling a reservation"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        result = service.cancel_reservation(res["id"])
        assert result["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, service):
        """Test that cancellation restores stock"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        service.cancel_reservation(res["id"])
        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 100

    def test_cancel_nonpending_fails(self, service):
        """Test that cancelling non-PENDING reservation fails"""
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key123")
        service.confirm_reservation(res["id"])
        with pytest.raises(ValueError, match="not in PENDING status"):
            service.cancel_reservation(res["id"])

    def test_cancel_nonexistent_fails(self, service):
        """Test that cancelling non-existent reservation returns None"""
        result = service.cancel_reservation(9999)
        assert result is None


class TestPagination:
    def test_get_orders_pagination(self, service):
        """Test paginated order retrieval"""
        service.create_sku("SKU001", 100)
        # Create and confirm 15 reservations
        for i in range(15):
            res = service.create_reservation("SKU001", 1, f"key{i}")
            service.confirm_reservation(res["id"])

        # Page 1 with size 10
        result = service.get_orders_paginated(1, 10)
        assert len(result["items"]) == 10
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 15

        # Page 2 with size 10
        result = service.get_orders_paginated(2, 10)
        assert len(result["items"]) == 5
        assert result["page"] == 2

    def test_orders_pagination_ordering(self, service):
        """Test that orders are returned in reverse chronological order"""
        service.create_sku("SKU001", 100)
        order_ids = []
        for i in range(3):
            res = service.create_reservation("SKU001", 1, f"key{i}")
            service.confirm_reservation(res["id"])
            order_ids.append(res["id"])

        result = service.get_orders_paginated(1, 10)
        # Most recent order should be first
        assert result["items"][0]["reservation_id"] == order_ids[-1]
