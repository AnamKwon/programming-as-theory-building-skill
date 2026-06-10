import pytest
from datetime import datetime, timedelta

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    InvalidReservationStateError,
    DuplicateIdempotencyKeyError,
)


@pytest.fixture
def repo():
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    return Service(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        assert sku.sku == "WIDGET-001"
        assert sku.quantity == 100

    def test_adjust_stock_increase(self, service):
        service.create_sku("WIDGET-001", 100)
        updated = service.adjust_stock("WIDGET-001", 50)
        assert updated.quantity == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("WIDGET-001", 100)
        updated = service.adjust_stock("WIDGET-001", -30)
        assert updated.quantity == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError):
            service.adjust_stock("NONEXISTENT", 10)

    def test_adjust_stock_negative_result(self, service):
        service.create_sku("WIDGET-001", 50)
        with pytest.raises(ValueError):
            service.adjust_stock("WIDGET-001", -100)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        assert reservation.sku == "WIDGET-001"
        assert reservation.quantity == 30
        assert reservation.status == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("WIDGET-001", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(
                sku="WIDGET-001",
                quantity=100,
                idempotency_key="key-1",
            )

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(ValueError):
            service.create_reservation(
                sku="NONEXISTENT",
                quantity=10,
                idempotency_key="key-1",
            )

    def test_create_reservation_idempotency(self, service):
        service.create_sku("WIDGET-001", 100)
        res1 = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )
        res2 = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        assert res1.reservation_id == res2.reservation_id
        assert res1.quantity == res2.quantity

    def test_create_reservation_idempotency_cancelled(self, service):
        service.create_sku("WIDGET-001", 100)
        res1 = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )
        service.cancel_reservation(res1.reservation_id)

        with pytest.raises(DuplicateIdempotencyKeyError):
            service.create_reservation(
                sku="WIDGET-001",
                quantity=30,
                idempotency_key="key-1",
            )

    def test_create_reservation_reduces_stock(self, service):
        service.create_sku("WIDGET-001", 100)
        service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        sku = service.repo.get_sku("WIDGET-001")
        assert sku.quantity == 70

    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        order = service.confirm_reservation(reservation.reservation_id)
        assert order.status == OrderStatus.CONFIRMED
        assert len(order.items) == 1
        assert order.items[0].sku == "WIDGET-001"
        assert order.items[0].quantity == 30

    def test_confirm_reservation_already_confirmed(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        order1 = service.confirm_reservation(reservation.reservation_id)
        order2 = service.confirm_reservation(reservation.reservation_id)

        assert order1.order_id == order2.order_id

    def test_confirm_reservation_expired(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation_id = service.repo.create_reservation(
            reservation_id="res-123",
            sku="WIDGET-001",
            quantity=30,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            idempotency_key="key-1",
        ).reservation_id

        with pytest.raises(InvalidReservationStateError):
            service.confirm_reservation(reservation_id)

    def test_cancel_reservation_happy_path(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        cancelled = service.cancel_reservation(reservation.reservation_id)
        assert cancelled.status == ReservationStatus.CANCELLED

    def test_cancel_reservation_restores_stock(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        service.cancel_reservation(reservation.reservation_id)
        sku = service.repo.get_sku("WIDGET-001")
        assert sku.quantity == 100

    def test_cancel_reservation_idempotent(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )

        service.cancel_reservation(reservation.reservation_id)
        cancelled2 = service.cancel_reservation(reservation.reservation_id)
        assert cancelled2.status == ReservationStatus.CANCELLED


class TestOrder:
    def test_get_order_happy_path(self, service):
        service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=30,
            idempotency_key="key-1",
        )
        order = service.confirm_reservation(reservation.reservation_id)

        retrieved = service.get_order(order.order_id)
        assert retrieved.order_id == order.order_id
        assert retrieved.status == OrderStatus.CONFIRMED

    def test_list_orders(self, service):
        service.create_sku("WIDGET-001", 100)
        service.create_sku("WIDGET-002", 100)

        res1 = service.create_reservation(
            sku="WIDGET-001",
            quantity=10,
            idempotency_key="key-1",
        )
        order1 = service.confirm_reservation(res1.reservation_id)

        res2 = service.create_reservation(
            sku="WIDGET-002",
            quantity=20,
            idempotency_key="key-2",
        )
        order2 = service.confirm_reservation(res2.reservation_id)

        orders, cursor = service.list_orders(limit=10)
        assert len(orders) == 2
        assert cursor is None

    def test_list_orders_pagination(self, service):
        service.create_sku("WIDGET-001", 1000)

        for i in range(25):
            res = service.create_reservation(
                sku="WIDGET-001",
                quantity=1,
                idempotency_key=f"key-{i}",
            )
            service.confirm_reservation(res.reservation_id)

        orders, cursor = service.list_orders(limit=20)
        assert len(orders) == 20
        assert cursor is not None

        orders2, cursor2 = service.list_orders(cursor=cursor, limit=20)
        assert len(orders2) == 5
        assert cursor2 is None
