"""Tests for service layer."""

import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    ReservationAlreadyConfirmedError,
)
from commerce_service.models import ReservationStatus, OrderStatus


@pytest.fixture
def repo():
    """Create an in-memory test repository."""
    repo = Repository(":memory:")
    yield repo


@pytest.fixture
def service(repo):
    """Create a service with test repository."""
    return CommerceService(repo)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("PROD-001", 100)
        assert result["sku"] == "PROD-001"
        assert result["stock_qty"] == 100

    def test_adjust_stock_increase(self, service):
        service.create_sku("PROD-001", 100)
        result = service.adjust_stock("PROD-001", 50)
        assert result["stock_qty"] == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("PROD-001", 100)
        result = service.adjust_stock("PROD-001", -30)
        assert result["stock_qty"] == 70

    def test_adjust_stock_negative(self, service):
        service.create_sku("PROD-001", 100)
        with pytest.raises(ValueError, match="cannot be negative"):
            service.adjust_stock("PROD-001", -150)

    def test_adjust_stock_sku_not_found(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    def test_reserve_inventory_success(self, service):
        service.create_sku("PROD-001", 100)
        result = service.reserve_inventory("PROD-001", 30, "key-1")
        assert result["sku"] == "PROD-001"
        assert result["qty"] == 30
        assert result["status"] == ReservationStatus.PENDING.value

    def test_reserve_inventory_decreases_stock(self, service):
        service.create_sku("PROD-001", 100)
        service.reserve_inventory("PROD-001", 30, "key-1")
        sku = service.repo.get_sku_by_code("PROD-001")
        assert sku["stock_qty"] == 70

    def test_reserve_inventory_insufficient_stock(self, service):
        service.create_sku("PROD-001", 20)
        with pytest.raises(InsufficientStockError):
            service.reserve_inventory("PROD-001", 30, "key-1")

    def test_reserve_inventory_idempotency(self, service):
        service.create_sku("PROD-001", 100)
        result1 = service.reserve_inventory("PROD-001", 30, "key-1")
        result2 = service.reserve_inventory("PROD-001", 50, "key-1")
        assert result1["id"] == result2["id"]
        assert result2["qty"] == 30  # Original qty, not 50
        sku = service.repo.get_sku_by_code("PROD-001")
        assert sku["stock_qty"] == 70  # Only deducted once

    def test_reserve_inventory_sku_not_found(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.reserve_inventory("NONEXISTENT", 10, "key-1")

    def test_reserve_inventory_expired_key_raises(self, service):
        service.create_sku("PROD-001", 100)
        repo = service.repo
        # Create an expired reservation
        expires_at = datetime.now() - timedelta(minutes=1)
        repo.create_reservation("PROD-001", 10, "expired-key", expires_at)
        repo.update_reservation_status(1, ReservationStatus.PENDING.value)

        with pytest.raises(ReservationExpiredError):
            service.reserve_inventory("PROD-001", 20, "expired-key")


class TestConfirmReservation:
    def test_confirm_reservation_creates_order(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        order = service.confirm_reservation(res["id"])
        assert order["sku"] == "PROD-001"
        assert order["qty"] == 30
        assert order["status"] == OrderStatus.PENDING.value

    def test_confirm_reservation_updates_status(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        service.confirm_reservation(res["id"])
        updated = service.repo.get_reservation_by_id(res["id"])
        assert updated["status"] == ReservationStatus.CONFIRMED.value

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_reservation_already_confirmed(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        service.confirm_reservation(res["id"])
        with pytest.raises(ReservationAlreadyConfirmedError):
            service.confirm_reservation(res["id"])

    def test_confirm_reservation_expired(self, service):
        service.create_sku("PROD-001", 100)
        repo = service.repo
        # Create an expired reservation
        expires_at = datetime.now() - timedelta(minutes=1)
        res = repo.create_reservation("PROD-001", 10, "expired-key", expires_at)

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res["id"])
        # Verify status was updated to expired
        updated = repo.get_reservation_by_id(res["id"])
        assert updated["status"] == ReservationStatus.EXPIRED.value


class TestCancelReservation:
    def test_cancel_reservation_releases_stock(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        service.cancel_reservation(res["id"])
        sku = service.repo.get_sku_by_code("PROD-001")
        assert sku["stock_qty"] == 100  # Stock restored

    def test_cancel_reservation_updates_status(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        service.cancel_reservation(res["id"])
        updated = service.repo.get_reservation_by_id(res["id"])
        assert updated["status"] == ReservationStatus.CANCELLED.value

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)

    def test_cancel_reservation_already_cancelled(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        service.cancel_reservation(res["id"])
        with pytest.raises(ValueError, match="already cancelled"):
            service.cancel_reservation(res["id"])

    def test_cancel_reservation_confirmed(self, service):
        service.create_sku("PROD-001", 100)
        res = service.reserve_inventory("PROD-001", 30, "key-1")
        service.confirm_reservation(res["id"])
        with pytest.raises(ValueError, match="Cannot cancel confirmed"):
            service.cancel_reservation(res["id"])


class TestOrderLookup:
    def test_get_orders_empty(self, service):
        result = service.get_orders()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["total_pages"] == 0

    def test_get_orders_pagination(self, service):
        service.create_sku("PROD-001", 1000)
        for i in range(25):
            res = service.reserve_inventory("PROD-001", 1, f"key-{i}")
            service.confirm_reservation(res["id"])

        page1 = service.get_orders(page=1, page_size=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 25
        assert page1["total_pages"] == 3

        page2 = service.get_orders(page=2, page_size=10)
        assert len(page2["items"]) == 10

        page3 = service.get_orders(page=3, page_size=10)
        assert len(page3["items"]) == 5

    def test_get_orders_invalid_page(self, service):
        with pytest.raises(ValueError):
            service.get_orders(page=0)

    def test_get_orders_invalid_page_size(self, service):
        with pytest.raises(ValueError):
            service.get_orders(page_size=0)
        with pytest.raises(ValueError):
            service.get_orders(page_size=101)
