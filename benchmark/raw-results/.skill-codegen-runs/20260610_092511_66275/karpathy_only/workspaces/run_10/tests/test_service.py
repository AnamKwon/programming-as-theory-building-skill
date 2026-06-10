import pytest
from datetime import datetime, timedelta

from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKUOperations:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU-001", "Laptop", 10)
        assert sku.sku == "SKU-001"
        assert sku.description == "Laptop"
        assert sku.quantity == 10

    def test_get_sku(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        sku = service.get_sku("SKU-001")
        assert sku.sku == "SKU-001"

    def test_get_nonexistent_sku(self, service):
        sku = service.get_sku("NONEXISTENT")
        assert sku is None

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        sku = service.adjust_stock("SKU-001", 5)
        assert sku.quantity == 15

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        sku = service.adjust_stock("SKU-001", -3)
        assert sku.quantity == 7

    def test_adjust_nonexistent_sku_raises(self, service):
        with pytest.raises(ValueError):
            service.adjust_stock("NONEXISTENT", 5)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        reservation = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        assert reservation.order_id == "ORD-001"
        assert reservation.sku == "SKU-001"
        assert reservation.quantity == 5
        assert reservation.status == "pending"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(
                order_id="ORD-001",
                sku="SKU-001",
                quantity=15,
                idempotency_key="IDEMPOTENT-001",
            )

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(ValueError):
            service.create_reservation(
                order_id="ORD-001",
                sku="NONEXISTENT",
                quantity=5,
                idempotency_key="IDEMPOTENT-001",
            )

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        res1 = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        res2 = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        assert res1.reservation_id == res2.reservation_id

    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        reservation = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        confirmed = service.confirm_reservation(reservation.reservation_id)
        assert confirmed.status == "confirmed"

        # Stock should be deducted
        sku = service.get_sku("SKU-001")
        assert sku.quantity == 5

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_confirm_reservation_expired(self, service, repo):
        service.create_sku("SKU-001", "Laptop", 10)
        reservation = repo.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
            ttl_seconds=0,  # Immediately expired
        )

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation.reservation_id)

    def test_confirm_already_confirmed_reservation(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        reservation = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        service.confirm_reservation(reservation.reservation_id)

        # Try to confirm again
        with pytest.raises(InvalidTransitionError):
            service.confirm_reservation(reservation.reservation_id)

    def test_cancel_reservation_happy_path(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        reservation = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        cancelled = service.cancel_reservation(reservation.reservation_id)
        assert cancelled.status == "cancelled"

        # Stock should NOT be affected (wasn't confirmed)
        sku = service.get_sku("SKU-001")
        assert sku.quantity == 10

    def test_cancel_confirmed_reservation_raises(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        reservation = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        service.confirm_reservation(reservation.reservation_id)

        with pytest.raises(InvalidTransitionError):
            service.cancel_reservation(reservation.reservation_id)

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")


class TestOrder:
    def test_get_order(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        order = service.get_order("ORD-001")
        assert order.order_id == "ORD-001"
        assert order.status == "pending"

    def test_get_nonexistent_order(self, service):
        with pytest.raises(ValueError):
            service.get_order("NONEXISTENT")

    def test_list_orders(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=5,
            idempotency_key="IDEMPOTENT-001",
        )
        service.create_reservation(
            order_id="ORD-002",
            sku="SKU-001",
            quantity=3,
            idempotency_key="IDEMPOTENT-002",
        )

        orders, total = service.list_orders(limit=10, offset=0)
        assert total == 2
        assert len(orders) == 2

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU-001", "Laptop", 100)
        for i in range(15):
            service.create_reservation(
                order_id=f"ORD-{i:03d}",
                sku="SKU-001",
                quantity=1,
                idempotency_key=f"IDEMPOTENT-{i:03d}",
            )

        orders1, total1 = service.list_orders(limit=10, offset=0)
        orders2, total2 = service.list_orders(limit=10, offset=10)

        assert total1 == 15
        assert len(orders1) == 10
        assert len(orders2) == 5

    def test_order_status_updated_on_all_reservations_confirmed(self, service):
        service.create_sku("SKU-001", "Laptop", 10)
        res1 = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=3,
            idempotency_key="IDEMPOTENT-001",
        )
        res2 = service.create_reservation(
            order_id="ORD-001",
            sku="SKU-001",
            quantity=2,
            idempotency_key="IDEMPOTENT-002",
        )

        service.confirm_reservation(res1.reservation_id)
        order = service.get_order("ORD-001")
        assert order.status == "pending"  # Not all confirmed yet

        service.confirm_reservation(res2.reservation_id)
        order = service.get_order("ORD-001")
        assert order.status == "confirmed"  # All confirmed
