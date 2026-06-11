"""Tests for the business logic layer."""

import pytest
import time
from datetime import datetime, timedelta

from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(db_path=":memory:")
    database.init_schema()
    return database


@pytest.fixture
def service(db):
    """Create a CommerceService instance for testing."""
    return CommerceService(db)


class TestSKUManagement:
    """Tests for SKU creation and management."""

    def test_create_sku(self, service):
        """Test creating a new SKU."""
        sku_id, sku_name, stock = service.create_sku("SKU001", 100)

        assert sku_id is not None
        assert sku_name == "SKU001"
        assert stock == 100

    def test_adjust_stock_positive(self, service):
        """Test adjusting stock with positive amount."""
        service.create_sku("SKU001", 100)
        new_stock = service.adjust_stock("SKU001", 50)

        assert new_stock == 150

    def test_adjust_stock_negative(self, service):
        """Test adjusting stock with negative amount."""
        service.create_sku("SKU001", 100)
        new_stock = service.adjust_stock("SKU001", -30)

        assert new_stock == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU returns None."""
        result = service.adjust_stock("NONEXISTENT", 10)

        assert result is None


class TestReservationCreation:
    """Tests for reservation creation with idempotency and stock validation."""

    def test_create_reservation_success(self, service):
        """Test happy path: create reservation successfully."""
        service.create_sku("SKU001", 100)
        success, res, error = service.create_reservation(
            "SKU001", 25, "idem-key-1"
        )

        assert success is True
        assert error is None
        assert res.id is not None
        assert res.sku == "SKU001"
        assert res.quantity == 25
        assert res.status == "PENDING"
        assert res.idempotency_key == "idem-key-1"

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation with insufficient stock returns 400."""
        service.create_sku("SKU001", 50)
        success, res, error = service.create_reservation(
            "SKU001", 100, "idem-key-1"
        )

        assert success is False
        assert error == "Insufficient stock"
        assert res is None

    def test_create_reservation_idempotency(self, service):
        """Test idempotent retry returns same reservation without double-deduction."""
        service.create_sku("SKU001", 100)

        # First request
        success1, res1, error1 = service.create_reservation(
            "SKU001", 25, "idem-key-1"
        )
        assert success1 is True

        # Second request with same idempotency key
        success2, res2, error2 = service.create_reservation(
            "SKU001", 25, "idem-key-1"
        )

        assert success2 is True
        assert res2.id == res1.id
        assert res2.quantity == res1.quantity
        assert res2.idempotency_key == res1.idempotency_key

        # Stock should only be deducted once (75 remaining, not 50)
        stock_check = service.adjust_stock("SKU001", 0)
        assert stock_check == 75

    def test_create_reservation_stock_deduction(self, service):
        """Test that stock is properly deducted after reservation."""
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 25, "idem-key-1")

        # Check remaining stock
        stock = service.adjust_stock("SKU001", 0)
        assert stock == 75


class TestReservationLifecycle:
    """Tests for reservation confirmation and cancellation."""

    def test_confirm_reservation_success(self, service):
        """Test confirming a pending reservation."""
        service.create_sku("SKU001", 100)
        _, res, _ = service.create_reservation("SKU001", 25, "idem-key-1")

        success, data, error = service.confirm_reservation(res.id)

        assert success is True
        assert error is None
        res_id, order_id, status = data
        assert status == "CONFIRMED"
        assert order_id is not None

    def test_confirm_reservation_non_pending(self, service):
        """Test confirming a non-pending reservation returns 400."""
        service.create_sku("SKU001", 100)
        _, res, _ = service.create_reservation("SKU001", 25, "idem-key-1")

        service.confirm_reservation(res.id)

        success, data, error = service.confirm_reservation(res.id)
        assert success is False
        assert "not in PENDING state" in error

    def test_confirm_reservation_expired(self, service):
        """Test confirming an expired reservation (>300 seconds old)."""
        service.create_sku("SKU001", 100)
        _, res, _ = service.create_reservation("SKU001", 25, "idem-key-1")

        # Manually set reservation as old by manipulating the database
        conn = service.db.get_connection()
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res.id),
        )
        conn.commit()

        success, data, error = service.confirm_reservation(res.id)

        assert success is False
        assert "expired" in error.lower()

        # Stock should be restored
        stock = service.adjust_stock("SKU001", 0)
        assert stock == 100

    def test_cancel_reservation_success(self, service):
        """Test cancelling a pending reservation."""
        service.create_sku("SKU001", 100)
        _, res, _ = service.create_reservation("SKU001", 25, "idem-key-1")

        success, data, error = service.cancel_reservation(res.id)

        assert success is True
        assert error is None
        res_id, status, restored_stock = data
        assert status == "CANCELLED"
        assert restored_stock == 25

        # Stock should be restored
        stock = service.adjust_stock("SKU001", 0)
        assert stock == 100

    def test_cancel_reservation_non_pending(self, service):
        """Test cancelling a non-pending reservation returns 400."""
        service.create_sku("SKU001", 100)
        _, res, _ = service.create_reservation("SKU001", 25, "idem-key-1")

        service.confirm_reservation(res.id)

        success, data, error = service.cancel_reservation(res.id)
        assert success is False
        assert "not in PENDING state" in error


class TestOrderManagement:
    """Tests for order retrieval and pagination."""

    def test_get_orders_empty(self, service):
        """Test getting orders when none exist."""
        orders, total, page_count = service.get_orders_paginated(1, 10)

        assert len(orders) == 0
        assert total == 0
        assert page_count == 1

    def test_get_orders_single_order(self, service):
        """Test getting a single order."""
        service.create_sku("SKU001", 100)
        _, res, _ = service.create_reservation("SKU001", 25, "idem-key-1")
        service.confirm_reservation(res.id)

        orders, total, page_count = service.get_orders_paginated(1, 10)

        assert len(orders) == 1
        assert total == 1
        assert page_count == 1
        assert orders[0].reservation_id == res.id

    def test_get_orders_pagination(self, service):
        """Test pagination offset behavior."""
        service.create_sku("SKU001", 10000)

        for i in range(25):
            _, res, _ = service.create_reservation("SKU001", 10, f"idem-key-{i}")
            service.confirm_reservation(res.id)

        page1, total, pages = service.get_orders_paginated(1, 10)
        page2, _, _ = service.get_orders_paginated(2, 10)
        page3, _, _ = service.get_orders_paginated(3, 10)

        assert total == 25
        assert pages == 3
        assert len(page1) == 10
        assert len(page2) == 10
        assert len(page3) == 5

        # Ensure different orders on each page
        page1_ids = {o.id for o in page1}
        page2_ids = {o.id for o in page2}
        page3_ids = {o.id for o in page3}

        assert len(page1_ids & page2_ids) == 0
        assert len(page2_ids & page3_ids) == 0
