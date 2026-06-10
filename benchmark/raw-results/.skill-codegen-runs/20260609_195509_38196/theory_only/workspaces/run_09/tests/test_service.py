"""Tests for service layer."""

import pytest
from datetime import datetime, timedelta

from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)
from src.commerce_service.models import ReservationStatus, OrderStatus


@pytest.fixture
def repo():
    """Create an in-memory test database."""
    db = Repository(":memory:")
    yield db
    db.clear_all()


@pytest.fixture
def service(repo):
    """Create a service instance with test database."""
    return CommerceService(repo)


class TestSKU:
    def test_create_sku(self, service):
        result = service.create_sku("widget", 100)
        assert result["id"] == 1
        assert result["name"] == "widget"
        assert result["quantity"] == 100

    def test_get_sku(self, service):
        service.create_sku("widget", 100)
        result = service.get_sku(1)
        assert result["id"] == 1
        assert result["quantity"] == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku("widget", 100)
        result = service.adjust_stock(1, 50)
        assert result["quantity"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("widget", 100)
        result = service.adjust_stock(1, -30)
        assert result["quantity"] == 70

    def test_adjust_stock_negative_to_zero_allowed(self, service):
        service.create_sku("widget", 100)
        result = service.adjust_stock(1, -100)
        assert result["quantity"] == 0

    def test_adjust_stock_negative_invalid(self, service):
        service.create_sku("widget", 100)
        with pytest.raises(ValueError, match="negative"):
            service.adjust_stock(1, -101)

    def test_get_sku_not_found(self, service):
        assert service.get_sku(999) is None


class TestReservation:
    def test_create_reservation_success(self, service):
        service.create_sku("widget", 100)
        result = service.create_reservation(1, 50, "key-1")
        assert result["id"] == 1
        assert result["sku_id"] == 1
        assert result["quantity"] == 50
        assert result["status"] == ReservationStatus.PENDING.value

        # Stock should be reduced
        sku = service.get_sku(1)
        assert sku["quantity"] == 50

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("widget", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(1, 100, "key-1")

    def test_create_reservation_idempotency(self, service):
        service.create_sku("widget", 100)
        res1 = service.create_reservation(1, 50, "key-1")
        res2 = service.create_reservation(1, 50, "key-1")
        assert res1["id"] == res2["id"]

        # Stock only reserved once
        sku = service.get_sku(1)
        assert sku["quantity"] == 50

    def test_get_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.get_reservation(999)

    def test_confirm_reservation_success(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")
        result = service.confirm_reservation(res["id"])
        assert result["status"] == ReservationStatus.CONFIRMED.value
        assert "order_id" in result

    def test_confirm_reservation_idempotent(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")
        res_id = res["id"]
        service.confirm_reservation(res_id)
        # Should fail on second attempt (not pending)
        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(res_id)

    def test_confirm_expired_reservation(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")

        # Manually expire the reservation
        past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        service.repo.repo._conn().__enter__().execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past, res["id"]),
        )
        service.repo.repo._conn().__enter__().commit()

        # Attempt to confirm should raise expiration error
        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res["id"])

        # Stock should be returned
        sku = service.get_sku(1)
        assert sku["quantity"] == 100

    def test_cancel_reservation_pending(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")
        result = service.cancel_reservation(res["id"])
        assert result["status"] == ReservationStatus.CANCELLED.value

        # Stock should be returned
        sku = service.get_sku(1)
        assert sku["quantity"] == 100

    def test_cancel_reservation_confirmed(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")
        service.confirm_reservation(res["id"])
        result = service.cancel_reservation(res["id"])
        assert result["status"] == ReservationStatus.CANCELLED.value

    def test_cancel_reservation_idempotent(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")
        service.cancel_reservation(res["id"])
        # Second cancel should succeed (idempotent)
        result = service.cancel_reservation(res["id"])
        assert result["status"] == ReservationStatus.CANCELLED.value


class TestOrder:
    def test_get_order(self, service):
        service.create_sku("widget", 100)
        res = service.create_reservation(1, 50, "key-1")
        service.confirm_reservation(res["id"])

        # Find the created order
        orders = service.list_orders()
        assert orders["total"] == 1
        order_id = orders["items"][0]["id"]

        result = service.get_order(order_id)
        assert result["sku_id"] == 1
        assert result["quantity"] == 50
        assert result["status"] == OrderStatus.CONFIRMED.value

    def test_list_orders_pagination(self, service):
        service.create_sku("widget", 100)

        # Create multiple reservations and confirm them
        for i in range(5):
            res = service.create_reservation(1, 10, f"key-{i}")
            service.confirm_reservation(res["id"])

        # Test pagination
        page1 = service.list_orders(offset=0, limit=2)
        assert len(page1["items"]) == 2
        assert page1["total"] == 5
        assert page1["offset"] == 0
        assert page1["limit"] == 2

        page2 = service.list_orders(offset=2, limit=2)
        assert len(page2["items"]) == 2

        page3 = service.list_orders(offset=4, limit=2)
        assert len(page3["items"]) == 1

    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["total"] == 0
        assert len(result["items"]) == 0
