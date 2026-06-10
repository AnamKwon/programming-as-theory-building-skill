"""Tests for the commerce service business logic."""

import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository, init_db
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidReservationStateError,
    ReservationExpiredError,
)


@pytest.fixture(scope="function")
def repo(monkeypatch, tmp_path):
    """Create an in-memory test repository."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("commerce_service.repository.DATABASE_PATH", db_file)
    init_db()
    return Repository()


@pytest.fixture(scope="function")
def service(repo):
    """Create a service instance with test repository."""
    return CommerceService(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        """Test creating a SKU with initial stock."""
        result = service.create_sku("SKU-001", 100)
        assert result["sku"] == "SKU-001"
        assert result["stock"] == 100

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", 50)
        assert result["new_stock"] == 150
        assert result["adjustment"] == 50

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", -30)
        assert result["new_stock"] == 70
        assert result["adjustment"] == -30

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(ValueError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        """Test creating a reservation with sufficient stock."""
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        assert result["id"] == 1
        assert result["sku"] == "SKU-001"
        assert result["quantity"] == 50
        assert result["status"] == "PENDING"

        stock = service.repo.get_sku_stock("SKU-001")
        assert stock == 50

    def test_create_reservation_insufficient_stock(self, service):
        """Test creating a reservation with insufficient stock."""
        service.create_sku("SKU-001", 100)

        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU-001", 150, "idempotency-key-1")

        stock = service.repo.get_sku_stock("SKU-001")
        assert stock == 100

    def test_idempotent_reservation(self, service):
        """Test idempotency: retry with same key returns same reservation."""
        service.create_sku("SKU-001", 100)
        result1 = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        stock_after_first = service.repo.get_sku_stock("SKU-001")

        result2 = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        stock_after_second = service.repo.get_sku_stock("SKU-001")

        assert result1["id"] == result2["id"]
        assert result1["created_at"] == result2["created_at"]
        assert stock_after_first == stock_after_second == 50

    def test_confirm_reservation_happy_path(self, service):
        """Test confirming a reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        result = service.confirm_reservation(reservation["id"])

        assert result["status"] == "CONFIRMED"
        assert "order_id" in result
        assert result["order_id"] == 1

        updated = service.repo.get_reservation(reservation["id"])
        assert updated["status"] == "CONFIRMED"

    def test_confirm_nonexistent_reservation(self, service):
        """Test confirming a non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_non_pending_reservation(self, service):
        """Test confirming a reservation that's not PENDING."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        service.confirm_reservation(reservation["id"])

        with pytest.raises(InvalidReservationStateError):
            service.confirm_reservation(reservation["id"])

    def test_expired_reservation(self, service):
        """Test that reservations older than 300 seconds cannot be confirmed."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        service.repo.set_reservation_created_at(reservation["id"], old_time)

        stock_before = service.repo.get_sku_stock("SKU-001")

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation["id"])

        stock_after = service.repo.get_sku_stock("SKU-001")
        assert stock_after == stock_before + 50

        updated = service.repo.get_reservation(reservation["id"])
        assert updated["status"] == "EXPIRED"

    def test_cancel_reservation_happy_path(self, service):
        """Test cancelling a reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        stock_before = service.repo.get_sku_stock("SKU-001")

        result = service.cancel_reservation(reservation["id"])

        assert result["status"] == "CANCELLED"
        assert result["restored_stock"] == 50

        stock_after = service.repo.get_sku_stock("SKU-001")
        assert stock_after == stock_before + 50

    def test_cancel_nonexistent_reservation(self, service):
        """Test cancelling a non-existent reservation."""
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)

    def test_cancel_non_pending_reservation(self, service):
        """Test cancelling a reservation that's not PENDING."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        service.confirm_reservation(reservation["id"])

        with pytest.raises(InvalidReservationStateError):
            service.cancel_reservation(reservation["id"])


class TestOrders:
    def test_list_orders_empty(self, service):
        """Test listing orders when none exist."""
        result = service.list_orders()
        assert result["total"] == 0
        assert result["items"] == []
        assert result["page"] == 1
        assert result["size"] == 10

    def test_list_orders_with_pagination(self, service):
        """Test listing orders with pagination."""
        service.create_sku("SKU-001", 100)

        for i in range(15):
            reservation = service.create_reservation("SKU-001", 1, f"key-{i}")
            service.confirm_reservation(reservation["id"])

        page1 = service.list_orders(page=1, size=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 15
        assert page1["page"] == 1

        page2 = service.list_orders(page=2, size=10)
        assert len(page2["items"]) == 5
        assert page2["total"] == 15
        assert page2["page"] == 2

    def test_order_created_on_confirm(self, service):
        """Test that an order is created when reservation is confirmed."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-key-1")

        service.confirm_reservation(reservation["id"])

        orders = service.list_orders()
        assert orders["total"] == 1
        assert orders["items"][0]["sku"] == "SKU-001"
        assert orders["items"][0]["quantity"] == 50
