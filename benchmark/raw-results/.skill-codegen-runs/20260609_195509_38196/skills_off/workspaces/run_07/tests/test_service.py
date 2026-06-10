import os
import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def temp_db():
    """Create a temporary database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def repo(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    return Service(repo)


class TestServiceHealthCheck:
    def test_health_check_success(self, service):
        result = service.health_check()
        assert result["status"] == "healthy"
        assert result["database"] == "ok"


class TestServiceSKU:
    def test_create_sku(self, service):
        result = service.create_sku("Widget", 29.99, stock=100)
        assert result.name == "Widget"
        assert result.price == 29.99
        assert result.current_stock == 100
        assert result.sku_id

    def test_adjust_stock_success(self, service):
        sku = service.create_sku("Gadget", 19.99, stock=50)
        result = service.adjust_stock(sku.sku_id, 25)
        assert result.current_stock == 75

    def test_adjust_stock_negative(self, service):
        sku = service.create_sku("Item", 9.99, stock=10)
        result = service.adjust_stock(sku.sku_id, -5)
        assert result.current_stock == 5

    def test_adjust_stock_not_found(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.adjust_stock("nonexistent", 10)


class TestServiceReservation:
    def test_reserve_success(self, service):
        sku = service.create_sku("Item", 9.99, stock=100)
        result = service.reserve(sku.sku_id, 10, "idempotency-key-1")

        assert result.reservation_id
        assert result.sku_id == sku.sku_id
        assert result.quantity == 10
        assert result.status == "RESERVED"
        assert result.idempotency_key == "idempotency-key-1"
        assert result.expires_at > datetime.utcnow()

    def test_reserve_insufficient_stock(self, service):
        sku = service.create_sku("Item", 9.99, stock=5)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.reserve(sku.sku_id, 10, "idempotency-key-2")

    def test_reserve_sku_not_found(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.reserve("nonexistent", 10, "idempotency-key-3")

    def test_reserve_idempotency(self, service):
        sku = service.create_sku("Item", 9.99, stock=100)
        result1 = service.reserve(sku.sku_id, 10, "idempotency-key-4")
        result2 = service.reserve(sku.sku_id, 20, "idempotency-key-4")

        assert result1.reservation_id == result2.reservation_id
        assert result2.quantity == 10  # Original quantity, not the second one


class TestServiceConfirmation:
    def test_confirm_reservation_success(self, service):
        sku = service.create_sku("Item", 9.99, stock=100)
        reservation = service.reserve(sku.sku_id, 10, "idempotency-key-5")

        order_id = service.confirm_reservation(reservation.reservation_id)
        assert order_id

        order = service.get_order(order_id)
        assert order.status == "CONFIRMED"
        assert len(order.items) == 1
        assert order.items[0].sku_id == sku.sku_id
        assert order.items[0].quantity == 10

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ValueError, match="Reservation not found"):
            service.confirm_reservation("nonexistent")

    def test_confirm_reservation_expired(self, service):
        sku = service.create_sku("Item", 9.99, stock=100)

        # Create reservation with 0 expiry minutes (already expired)
        result = service.repo.reserve(sku.sku_id, 10, "idempotency-key-6", expiry_minutes=0)

        with pytest.raises(ValueError, match="Reservation expired"):
            service.confirm_reservation(result.reservation_id)

    def test_confirm_reservation_already_confirmed(self, service):
        sku = service.create_sku("Item", 9.99, stock=100)
        reservation = service.reserve(sku.sku_id, 10, "idempotency-key-7")
        service.confirm_reservation(reservation.reservation_id)

        with pytest.raises(ValueError, match="cannot confirm"):
            service.confirm_reservation(reservation.reservation_id)


class TestServiceCancellation:
    def test_cancel_reservation_success(self, service):
        sku = service.create_sku("Item", 9.99, stock=100)
        reservation = service.reserve(sku.sku_id, 10, "idempotency-key-8")

        result = service.cancel_reservation(reservation.reservation_id)
        assert result is True

    def test_cancel_reservation_not_found(self, service):
        result = service.cancel_reservation("nonexistent")
        assert result is False


class TestServiceOrderListing:
    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result.orders == []
        assert result.total == 0
        assert result.skip == 0
        assert result.limit == 10

    def test_list_orders_with_pagination(self, service):
        sku = service.create_sku("Item", 9.99, stock=200)

        for i in range(15):
            reservation = service.reserve(sku.sku_id, 5, f"key-{i}")
            service.confirm_reservation(reservation.reservation_id)

        result1 = service.list_orders(skip=0, limit=10)
        assert len(result1.orders) == 10
        assert result1.total == 15

        result2 = service.list_orders(skip=10, limit=10)
        assert len(result2.orders) == 5
        assert result2.total == 15
