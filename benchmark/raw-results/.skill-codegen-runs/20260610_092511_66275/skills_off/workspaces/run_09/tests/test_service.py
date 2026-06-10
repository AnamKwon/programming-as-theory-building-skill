import os
import tempfile
import pytest
from datetime import datetime, timedelta, timezone

from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repository(temp_db):
    return Repository(database_url=temp_db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


class TestSkuAndStock:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", "Widget A")
        assert result["code"] == "SKU001"
        assert result["name"] == "Widget A"
        assert result["id"] is not None

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU001", "Widget A")
        result = service.adjust_stock(1, 100)
        assert result["quantity_available"] == 100

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)
        result = service.adjust_stock(1, -30)
        assert result["quantity_available"] == 70

    def test_adjust_stock_clamp_to_zero(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)
        result = service.adjust_stock(1, -150)
        assert result["quantity_available"] == 0

    def test_adjust_stock_invalid_sku(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock(999, 10)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        result = service.create_reservation(1, 50, "idempotency_key_1")

        assert result["status"] == "pending"
        assert len(result["reservations"]) == 1
        assert result["reservations"][0]["quantity"] == 50
        assert result["reservations"][0]["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 50)

        with pytest.raises(InsufficientStockError):
            service.create_reservation(1, 100, "idempotency_key_1")

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        result1 = service.create_reservation(1, 50, "idempotency_key_1")
        result2 = service.create_reservation(1, 50, "idempotency_key_1")

        assert result1["id"] == result2["id"]
        assert result1["reservations"][0]["id"] == result2["reservations"][0]["id"]

    def test_create_reservation_insufficient_stock_after_first_reservation(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        service.create_reservation(1, 80, "idempotency_key_1")

        with pytest.raises(InsufficientStockError):
            service.create_reservation(1, 50, "idempotency_key_2")

    def test_create_reservation_invalid_sku(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation(999, 10, "idempotency_key_1")


class TestReservationConfirmation:
    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        order = service.create_reservation(1, 50, "idempotency_key_1")
        reservation_id = order["reservations"][0]["id"]

        confirmed_order = service.confirm_reservation(reservation_id)

        assert confirmed_order["status"] == "confirmed"
        assert confirmed_order["reservations"][0]["status"] == "confirmed"

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_reservation_invalid_state(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        order = service.create_reservation(1, 50, "idempotency_key_1")
        reservation_id = order["reservations"][0]["id"]

        service.confirm_reservation(reservation_id)

        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(reservation_id)


class TestReservationCancellation:
    def test_cancel_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        order = service.create_reservation(1, 50, "idempotency_key_1")
        reservation_id = order["reservations"][0]["id"]

        cancelled_order = service.cancel_reservation(reservation_id)

        assert cancelled_order["status"] == "cancelled"
        assert cancelled_order["reservations"][0]["status"] == "cancelled"

    def test_cancel_reservation_returns_stock(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        order = service.create_reservation(1, 50, "idempotency_key_1")
        reservation_id = order["reservations"][0]["id"]

        service.cancel_reservation(reservation_id)

        stock = service.adjust_stock(1, 0)
        assert stock["quantity_available"] == 100

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)

    def test_cancel_reservation_invalid_state(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        order = service.create_reservation(1, 50, "idempotency_key_1")
        reservation_id = order["reservations"][0]["id"]

        service.cancel_reservation(reservation_id)

        with pytest.raises(InvalidStateTransitionError):
            service.cancel_reservation(reservation_id)


class TestOrderLookup:
    def test_get_orders_pagination(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 1000)

        for i in range(15):
            service.create_reservation(1, 10, f"idempotency_key_{i}")

        result_page1 = service.get_orders(page=1, page_size=10)
        assert len(result_page1["orders"]) == 10
        assert result_page1["total"] == 15
        assert result_page1["page"] == 1

        result_page2 = service.get_orders(page=2, page_size=10)
        assert len(result_page2["orders"]) == 5
        assert result_page2["total"] == 15
        assert result_page2["page"] == 2

    def test_get_order_by_id(self, service):
        service.create_sku("SKU001", "Widget A")
        service.adjust_stock(1, 100)

        created_order = service.create_reservation(1, 50, "idempotency_key_1")
        order_id = created_order["id"]

        retrieved_order = service.get_order(order_id)

        assert retrieved_order["id"] == order_id
        assert retrieved_order["status"] == "pending"
        assert len(retrieved_order["reservations"]) == 1

    def test_get_order_not_found(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.get_order(999)
