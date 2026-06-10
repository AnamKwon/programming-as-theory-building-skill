import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.models import ReservationStatus, OrderStatus
from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    os.unlink(path)


@pytest.fixture
def service(temp_db):
    return CommerceService(temp_db)


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", "Widget", 100)
        assert result["sku_id"] == "SKU001"
        assert result["name"] == "Widget"
        assert result["stock_quantity"] == 100

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("SKU001", "Widget", 100)
        with pytest.raises(Exception) as exc_info:
            service.create_sku("SKU001", "Widget", 100)
        assert "already exists" in str(exc_info.value)

    def test_get_nonexistent_sku_fails(self, service):
        with pytest.raises(Exception) as exc_info:
            service.get_sku("NONEXISTENT")
        assert "not found" in str(exc_info.value)

    def test_adjust_stock(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["stock_quantity"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["stock_quantity"] == 70

    def test_adjust_stock_below_zero_fails(self, service):
        service.create_sku("SKU001", "Widget", 10)
        with pytest.raises(Exception) as exc_info:
            service.adjust_stock("SKU001", -20)
        assert "negative" in str(exc_info.value)


class TestReservations:
    def test_create_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result = service.create_reservation("SKU001", 10, "idempotency-1")

        assert result["sku_id"] == "SKU001"
        assert result["quantity"] == 10
        assert result["status"] == ReservationStatus.PENDING.value
        assert "reservation_id" in result

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result1 = service.create_reservation("SKU001", 10, "idempotency-1")
        result2 = service.create_reservation("SKU001", 10, "idempotency-1")

        assert result1["reservation_id"] == result2["reservation_id"]

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Widget", 5)
        with pytest.raises(Exception) as exc_info:
            service.create_reservation("SKU001", 10, "idempotency-1")
        assert "Insufficient stock" in str(exc_info.value)

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(Exception) as exc_info:
            service.create_reservation("NONEXISTENT", 10, "idempotency-1")
        assert "not found" in str(exc_info.value)

    def test_confirm_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")

        result = service.confirm_reservation(reservation["reservation_id"])
        assert result["status"] == ReservationStatus.CONFIRMED.value

    def test_confirm_reservation_reduces_stock(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")
        service.confirm_reservation(reservation["reservation_id"])

        sku = service.get_sku("SKU001")
        assert sku["stock_quantity"] == 90

    def test_confirm_expired_reservation_fails(self, service, temp_db):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")

        # Manually expire the reservation
        now = datetime.utcnow()
        temp_db.db.execute(
            "UPDATE reservations SET expires_at = ? WHERE reservation_id = ?",
            (
                (now - timedelta(seconds=1)).isoformat(),
                reservation["reservation_id"],
            ),
        )

        with pytest.raises(Exception) as exc_info:
            service.confirm_reservation(reservation["reservation_id"])
        assert "expired" in str(exc_info.value)

    def test_cancel_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")

        result = service.cancel_reservation(reservation["reservation_id"])
        assert result["status"] == ReservationStatus.CANCELLED.value

    def test_cancel_nonexistent_reservation_fails(self, service):
        with pytest.raises(Exception) as exc_info:
            service.cancel_reservation("NONEXISTENT")
        assert "not found" in str(exc_info.value)

    def test_cannot_confirm_cancelled_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")
        service.cancel_reservation(reservation["reservation_id"])

        with pytest.raises(Exception) as exc_info:
            service.confirm_reservation(reservation["reservation_id"])
        assert "cannot confirm" in str(exc_info.value).lower()


class TestOrders:
    def test_create_order_via_confirmation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")
        service.confirm_reservation(reservation["reservation_id"])

        orders, total = service.list_orders(20, 0)
        assert len(orders) == 1
        assert orders[0]["sku_id"] == "SKU001"
        assert orders[0]["quantity"] == 10
        assert orders[0]["status"] == OrderStatus.PENDING.value

    def test_get_order(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 10, "idempotency-1")
        service.confirm_reservation(reservation["reservation_id"])

        orders, _ = service.list_orders(20, 0)
        order = service.get_order(orders[0]["order_id"])

        assert order["sku_id"] == "SKU001"
        assert order["quantity"] == 10

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU001", "Widget", 1000)

        # Create multiple orders
        for i in range(5):
            reservation = service.create_reservation("SKU001", 10, f"idempotency-{i}")
            service.confirm_reservation(reservation["reservation_id"])

        orders, total = service.list_orders(limit=2, offset=0)
        assert len(orders) == 2
        assert total == 5

        orders_page2, _ = service.list_orders(limit=2, offset=2)
        assert len(orders_page2) == 2
        assert orders[0]["order_id"] != orders_page2[0]["order_id"]

    def test_list_orders_invalid_limit_fails(self, service):
        with pytest.raises(Exception) as exc_info:
            service.list_orders(limit=0, offset=0)
        assert "Limit must be between" in str(exc_info.value)

    def test_list_orders_invalid_offset_fails(self, service):
        with pytest.raises(Exception) as exc_info:
            service.list_orders(limit=20, offset=-1)
        assert "Offset must be non-negative" in str(exc_info.value)
