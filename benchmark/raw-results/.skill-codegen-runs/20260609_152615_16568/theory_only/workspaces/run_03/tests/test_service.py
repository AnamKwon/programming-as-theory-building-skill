"""Tests for the commerce service business logic."""

import pytest

from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationAlreadyExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKUCreation:
    def test_create_sku(self, service):
        result = service.create_sku("SKU123", "Test Product")
        assert result["sku_id"] == "SKU123"
        assert result["name"] == "Test Product"

    def test_adjust_stock_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)

    def test_adjust_stock_success(self, service):
        service.create_sku("SKU123", "Test Product")
        result = service.adjust_stock("SKU123", 100)
        assert result["new_available"] == 100
        assert result["sku_id"] == "SKU123"

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)
        result = service.adjust_stock("SKU123", -30)
        assert result["new_available"] == 70


class TestReservation:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        result = service.create_reservation("ORDER1", "SKU123", 10, "KEY1")
        assert result["order_id"] == "ORDER1"
        assert result["sku_id"] == "SKU123"
        assert result["quantity"] == 10
        assert result["status"] == ReservationStatus.PENDING.value

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("ORDER1", "NONEXISTENT", 10, "KEY1")

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        with pytest.raises(InsufficientStockError):
            service.create_reservation("ORDER1", "SKU123", 150, "KEY1")

    def test_reservation_idempotency(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        # First reservation
        result1 = service.create_reservation("ORDER1", "SKU123", 10, "KEY1")
        res_id1 = result1["id"]

        # Same idempotency key returns existing reservation
        result2 = service.create_reservation("ORDER2", "SKU123", 20, "KEY1")
        res_id2 = result2["id"]

        assert res_id1 == res_id2
        assert result2["status"] == ReservationStatus.PENDING.value

    def test_confirm_reservation(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        result1 = service.create_reservation("ORDER1", "SKU123", 10, "KEY1")
        res_id = result1["id"]

        result2 = service.confirm_reservation(res_id)
        assert result2["status"] == ReservationStatus.CONFIRMED.value

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_cancel_reservation(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        result1 = service.create_reservation("ORDER1", "SKU123", 10, "KEY1")
        res_id = result1["id"]

        result2 = service.cancel_reservation(res_id)
        assert result2["status"] == ReservationStatus.CANCELLED.value

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")

    def test_cancel_releases_stock(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        # Create two reservations
        result1 = service.create_reservation("ORDER1", "SKU123", 50, "KEY1")
        result2 = service.create_reservation("ORDER2", "SKU123", 50, "KEY2")

        # Both should succeed (100 total available)
        assert result1["status"] == ReservationStatus.PENDING.value
        assert result2["status"] == ReservationStatus.PENDING.value

        # Cancel first reservation
        service.cancel_reservation(result1["id"])

        # Should be able to create another 50-unit reservation
        result3 = service.create_reservation("ORDER3", "SKU123", 50, "KEY3")
        assert result3["status"] == ReservationStatus.PENDING.value


class TestOrder:
    def test_get_order_with_reservations(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        service.create_reservation("ORDER1", "SKU123", 10, "KEY1")
        service.create_reservation("ORDER1", "SKU124", 5, "KEY2")

        # Create second SKU
        service.create_sku("SKU124", "Another Product")
        service.adjust_stock("SKU124", 50)

        # Retry second reservation
        result = service.create_reservation("ORDER1", "SKU124", 5, "KEY2")

        order = service.get_order("ORDER1")
        assert order is not None
        assert order["order"]["id"] == "ORDER1"
        assert len(order["reservations"]) == 2

    def test_get_nonexistent_order(self, service):
        order = service.get_order("NONEXISTENT")
        assert order is None

    def test_list_orders(self, service):
        service.create_sku("SKU123", "Test Product")
        service.adjust_stock("SKU123", 100)

        for i in range(15):
            service.create_reservation(f"ORDER{i}", "SKU123", 1, f"KEY{i}")

        # Test pagination
        result1 = service.list_orders(offset=0, limit=10)
        assert len(result1["orders"]) == 10
        assert result1["total"] == 15
        assert result1["offset"] == 0
        assert result1["limit"] == 10

        result2 = service.list_orders(offset=10, limit=10)
        assert len(result2["orders"]) == 5
        assert result2["total"] == 15

    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["orders"] == []
        assert result["total"] == 0
