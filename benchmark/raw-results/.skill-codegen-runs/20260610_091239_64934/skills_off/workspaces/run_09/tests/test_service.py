"""Tests for service layer."""

import pytest
from datetime import datetime, timedelta

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create a fresh test database."""
    repo = Repository(":memory:")
    yield repo
    repo.cleanup_db()


@pytest.fixture
def service(db):
    """Create service with test repository."""
    return CommerceService(db)


class TestSKUCreation:
    def test_create_sku(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget")
        assert sku["code"] == "WIDGET-001"
        assert sku["name"] == "Blue Widget"
        assert sku["id"] > 0

    def test_get_sku(self, service):
        sku = service.create_sku("WIDGET-002", "Red Widget")
        fetched = service.get_sku(sku["id"])
        assert fetched["code"] == "WIDGET-002"

    def test_get_nonexistent_sku_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.get_sku(999)


class TestStockManagement:
    def test_adjust_stock_increase(self, service):
        sku = service.create_sku("WIDGET-003", "Green Widget")
        result = service.adjust_stock(sku["id"], 100)
        assert result["quantity"] == 100
        assert result["available"] == 100

    def test_adjust_stock_decrease(self, service):
        sku = service.create_sku("WIDGET-004", "Yellow Widget")
        service.adjust_stock(sku["id"], 100)
        result = service.adjust_stock(sku["id"], -30)
        assert result["quantity"] == 70
        assert result["available"] == 70

    def test_adjust_stock_nonexistent_sku_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock(999, 10)


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        sku = service.create_sku("WIDGET-005", "Purple Widget")
        service.adjust_stock(sku["id"], 50)
        order = service.create_order()

        res = service.create_reservation(
            order["id"], sku["id"], 10, "idem-001", expires_in_seconds=3600
        )

        assert res["status"] == ReservationStatus.PENDING
        assert res["quantity"] == 10
        assert res["sku_id"] == sku["id"]

    def test_insufficient_stock_raises(self, service):
        sku = service.create_sku("WIDGET-006", "Orange Widget")
        service.adjust_stock(sku["id"], 5)
        order = service.create_order()

        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation(
                order["id"], sku["id"], 10, "idem-002"
            )

    def test_idempotent_reservation_retry(self, service):
        sku = service.create_sku("WIDGET-007", "Pink Widget")
        service.adjust_stock(sku["id"], 50)
        order = service.create_order()

        res1 = service.create_reservation(
            order["id"], sku["id"], 10, "idem-003"
        )
        res2 = service.create_reservation(
            order["id"], sku["id"], 10, "idem-003"
        )

        assert res1["id"] == res2["id"]

    def test_expired_reservation_rejected(self, service, db):
        sku = service.create_sku("WIDGET-008", "Brown Widget")
        service.adjust_stock(sku["id"], 50)
        order = service.create_order()

        res = service.create_reservation(
            order["id"], sku["id"], 10, "idem-004", expires_in_seconds=1
        )
        past_time = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
        db.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past_time, res["id"])
        )
        db._conn().__enter__()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res["id"])

    def test_confirm_reservation(self, service):
        sku = service.create_sku("WIDGET-009", "Silver Widget")
        service.adjust_stock(sku["id"], 50)
        order = service.create_order()

        res = service.create_reservation(
            order["id"], sku["id"], 10, "idem-005"
        )

        confirmed = service.confirm_reservation(res["id"])
        assert confirmed["status"] == ReservationStatus.CONFIRMED

    def test_cancel_reservation(self, service, db):
        sku = service.create_sku("WIDGET-010", "Gold Widget")
        service.adjust_stock(sku["id"], 50)
        order = service.create_order()

        res = service.create_reservation(
            order["id"], sku["id"], 10, "idem-006"
        )

        cancelled = service.cancel_reservation(res["id"])
        assert cancelled["status"] == ReservationStatus.CANCELLED

        stock = db.get_stock(sku["id"])
        assert stock["reserved"] == 0

    def test_cannot_confirm_expired_then_expires(self, service, db):
        sku = service.create_sku("WIDGET-011", "Copper Widget")
        service.adjust_stock(sku["id"], 50)
        order = service.create_order()

        res = service.create_reservation(
            order["id"], sku["id"], 10, "idem-007", expires_in_seconds=1
        )
        past_time = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
        db.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past_time, res["id"])
        )
        db._conn().__enter__()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res["id"])


class TestOrders:
    def test_create_order(self, service):
        order = service.create_order()
        assert order["status"] == OrderStatus.PENDING
        assert order["id"] > 0

    def test_get_order_with_items(self, service):
        sku1 = service.create_sku("WIDGET-012", "Item1")
        sku2 = service.create_sku("WIDGET-013", "Item2")
        service.adjust_stock(sku1["id"], 100)
        service.adjust_stock(sku2["id"], 100)
        order = service.create_order()

        res1 = service.create_reservation(
            order["id"], sku1["id"], 5, "idem-008"
        )
        res2 = service.create_reservation(
            order["id"], sku2["id"], 3, "idem-009"
        )

        fetched = service.get_order(order["id"])
        assert fetched["id"] == order["id"]
        assert len(fetched["items"]) == 2

    def test_list_orders_pagination(self, service):
        for i in range(25):
            order = service.create_order()
            assert order["id"] > 0

        page1 = service.list_orders(skip=0, limit=20)
        assert page1["total"] == 25
        assert len(page1["items"]) == 20
        assert page1["skip"] == 0
        assert page1["limit"] == 20

        page2 = service.list_orders(skip=20, limit=20)
        assert len(page2["items"]) == 5
