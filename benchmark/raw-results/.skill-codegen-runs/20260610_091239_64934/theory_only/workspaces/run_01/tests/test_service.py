import json
from datetime import datetime, timedelta

import pytest

from commerce_service.models import OrderState, ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    OrderNotFoundError,
    ReservationExpiredError,
    ReservationNotFoundError,
    ReservationStateError,
    ServiceError,
)


@pytest.fixture
def repository():
    return Repository()


@pytest.fixture
def service(repository):
    return CommerceService(repository)


class TestSKU:
    def test_create_sku(self, service):
        sku = service.create_sku("PROD-001", 100)
        assert sku.sku_id == "PROD-001"
        assert sku.available_stock == 100
        assert sku.reserved_stock == 0

    def test_get_sku(self, service):
        service.create_sku("PROD-002", 50)
        sku = service.get_sku("PROD-002")
        assert sku.available_stock == 50

    def test_get_nonexistent_sku_raises(self, service):
        with pytest.raises(ServiceError):
            service.get_sku("NONEXISTENT")

    def test_adjust_stock_add(self, service):
        service.create_sku("PROD-003", 100)
        result = service.adjust_stock("PROD-003", 50)
        assert result.available_stock == 150

    def test_adjust_stock_subtract(self, service):
        service.create_sku("PROD-004", 100)
        result = service.adjust_stock("PROD-004", -30)
        assert result.available_stock == 70

    def test_adjust_stock_below_zero_raises(self, service):
        service.create_sku("PROD-005", 100)
        with pytest.raises(ServiceError):
            service.adjust_stock("PROD-005", -150)


class TestReservation:
    def test_create_reservation_succeeds(self, service):
        service.create_sku("PROD-006", 100)
        reservation = service.create_reservation("PROD-006", 30, "idempotent-1", 300)

        assert reservation.sku_id == "PROD-006"
        assert reservation.quantity == 30
        assert reservation.state == ReservationState.PENDING
        assert reservation.expires_at is not None

    def test_create_reservation_reserves_stock(self, service):
        service.create_sku("PROD-007", 100)
        service.create_reservation("PROD-007", 30, "idempotent-2", 300)

        sku = service.get_sku("PROD-007")
        assert sku.available_stock == 70
        assert sku.reserved_stock == 30

    def test_create_reservation_insufficient_stock_raises(self, service):
        service.create_sku("PROD-008", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("PROD-008", 100, "idempotent-3", 300)

    def test_create_reservation_idempotent(self, service):
        service.create_sku("PROD-009", 100)
        res1 = service.create_reservation("PROD-009", 20, "idempotent-4", 300)
        res2 = service.create_reservation("PROD-009", 999, "idempotent-4", 300)

        assert res1.reservation_id == res2.reservation_id
        sku = service.get_sku("PROD-009")
        assert sku.reserved_stock == 20

    def test_confirm_reservation_succeeds(self, service):
        service.create_sku("PROD-010", 100)
        res = service.create_reservation("PROD-010", 20, "idempotent-5", 300)

        confirmed = service.confirm_reservation(res.reservation_id, "idempotent-6")
        assert confirmed.state == ReservationState.CONFIRMED

    def test_confirm_reservation_idempotent(self, service):
        service.create_sku("PROD-011", 100)
        res = service.create_reservation("PROD-011", 20, "idempotent-7", 300)

        confirmed1 = service.confirm_reservation(res.reservation_id, "idempotent-8")
        confirmed2 = service.confirm_reservation(res.reservation_id, "idempotent-8")

        assert confirmed1.state == ReservationState.CONFIRMED
        assert confirmed2.state == ReservationState.CONFIRMED

    def test_confirm_nonexistent_raises(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT", "idempotent-9")

    def test_confirm_already_confirmed_raises(self, service):
        service.create_sku("PROD-012", 100)
        res = service.create_reservation("PROD-012", 20, "idempotent-10", 300)
        service.confirm_reservation(res.reservation_id, "idempotent-11")

        with pytest.raises(ReservationStateError):
            service.confirm_reservation(res.reservation_id, "idempotent-12")

    def test_expired_reservation_cancels_on_confirm(self, service):
        service.create_sku("PROD-013", 100)
        res = service.create_reservation("PROD-013", 20, "idempotent-13", 1)

        import time

        time.sleep(1.1)

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.reservation_id, "idempotent-14")

        sku = service.get_sku("PROD-013")
        assert sku.reserved_stock == 0
        assert sku.available_stock == 100

    def test_cancel_reservation_succeeds(self, service):
        service.create_sku("PROD-014", 100)
        res = service.create_reservation("PROD-014", 20, "idempotent-15", 300)

        cancelled = service.cancel_reservation(res.reservation_id)
        assert cancelled.state == ReservationState.CANCELLED

        sku = service.get_sku("PROD-014")
        assert sku.reserved_stock == 0
        assert sku.available_stock == 100

    def test_cancel_nonexistent_raises(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")

    def test_cancel_already_cancelled_is_idempotent(self, service):
        service.create_sku("PROD-015", 100)
        res = service.create_reservation("PROD-015", 20, "idempotent-16", 300)
        service.cancel_reservation(res.reservation_id)

        result = service.cancel_reservation(res.reservation_id)
        assert result.state == ReservationState.CANCELLED


class TestOrder:
    def test_create_order_succeeds(self, service):
        service.create_sku("PROD-016", 100)
        res = service.create_reservation("PROD-016", 20, "idempotent-17", 300)
        service.confirm_reservation(res.reservation_id, "idempotent-18")

        order = service.create_order([res.reservation_id], "idempotent-19")
        assert order.order_id is not None
        assert res.reservation_id in order.reservation_ids
        assert order.state == OrderState.PENDING

    def test_create_order_with_multiple_reservations(self, service):
        service.create_sku("PROD-017", 100)
        service.create_sku("PROD-018", 100)

        res1 = service.create_reservation("PROD-017", 20, "idempotent-20", 300)
        res2 = service.create_reservation("PROD-018", 30, "idempotent-21", 300)

        service.confirm_reservation(res1.reservation_id, "idempotent-22")
        service.confirm_reservation(res2.reservation_id, "idempotent-23")

        order = service.create_order(
            [res1.reservation_id, res2.reservation_id], "idempotent-24"
        )
        assert len(order.reservation_ids) == 2

    def test_create_order_requires_confirmed_reservation(self, service):
        service.create_sku("PROD-019", 100)
        res = service.create_reservation("PROD-019", 20, "idempotent-25", 300)

        with pytest.raises(ReservationStateError):
            service.create_order([res.reservation_id], "idempotent-26")

    def test_create_order_idempotent(self, service):
        service.create_sku("PROD-020", 100)
        res = service.create_reservation("PROD-020", 20, "idempotent-27", 300)
        service.confirm_reservation(res.reservation_id, "idempotent-28")

        order1 = service.create_order([res.reservation_id], "idempotent-29")
        order2 = service.create_order([res.reservation_id], "idempotent-29")

        assert order1.order_id == order2.order_id

    def test_get_order(self, service):
        service.create_sku("PROD-021", 100)
        res = service.create_reservation("PROD-021", 20, "idempotent-30", 300)
        service.confirm_reservation(res.reservation_id, "idempotent-31")
        order = service.create_order([res.reservation_id], "idempotent-32")

        retrieved = service.get_order(order.order_id)
        assert retrieved.order_id == order.order_id
        assert retrieved.state == OrderState.PENDING

    def test_get_nonexistent_order_raises(self, service):
        with pytest.raises(OrderNotFoundError):
            service.get_order("NONEXISTENT")

    def test_list_orders_empty(self, service):
        orders, total = service.list_orders()
        assert total == 0
        assert len(orders) == 0

    def test_list_orders_with_pagination(self, service):
        service.create_sku("PROD-022", 100)

        for i in range(15):
            res = service.create_reservation("PROD-022", 1, f"idempotent-{i}", 300)
            service.confirm_reservation(res.reservation_id, f"idempotent-confirm-{i}")
            service.create_order([res.reservation_id], f"idempotent-order-{i}")

        page1, total = service.list_orders(page=1, page_size=10)
        assert len(page1) == 10
        assert total == 15

        page2, _ = service.list_orders(page=2, page_size=10)
        assert len(page2) == 5


class TestCleanup:
    def test_cleanup_expired_reservations(self, service):
        service.create_sku("PROD-023", 100)
        res1 = service.create_reservation("PROD-023", 20, "idempotent-33", 1)
        res2 = service.create_reservation("PROD-023", 30, "idempotent-34", 300)

        import time

        time.sleep(1.1)

        count = service.cleanup_expired_reservations()
        assert count == 1

        sku = service.get_sku("PROD-023")
        assert sku.available_stock == 70
        assert sku.reserved_stock == 30

        expired_res = service.repo.get_reservation(res1.reservation_id)
        assert expired_res.state == ReservationState.CANCELLED
