import pytest
from datetime import datetime, timedelta

from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService
from src.commerce_service.models import ReservationState, OrderState


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def service(db):
    return CommerceService(db)


class TestSKUCreation:
    def test_create_sku_succeeds(self, service):
        sku = service.create_sku("WIDGET-001", "Premium Widget")
        assert sku["sku"] == "WIDGET-001"
        assert sku["name"] == "Premium Widget"

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        result = service.create_sku("WIDGET-001", "Another Widget")
        assert result is None


class TestInventoryAdjustment:
    def test_adjust_stock_for_existing_sku(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        result = service.adjust_stock("WIDGET-001", 100)
        assert result["quantity"] == 100

    def test_adjust_stock_for_nonexistent_sku(self, service):
        result = service.adjust_stock("NONEXISTENT", 100)
        assert result is None

    def test_negative_adjustment(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)
        result = service.adjust_stock("WIDGET-001", -30)
        assert result["quantity"] == 70


class TestReservation:
    def test_create_reservation_succeeds(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)

        reservation, error = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )
        assert error is None
        assert reservation["sku"] == "WIDGET-001"
        assert reservation["quantity"] == 10
        assert reservation["state"] == ReservationState.PENDING
        assert datetime.fromisoformat(reservation["expires_at"]) > datetime.utcnow()

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 5)

        reservation, error = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )
        assert error is not None
        assert "Insufficient stock" in error
        assert reservation is None

    def test_create_reservation_nonexistent_sku(self, service):
        reservation, error = service.create_reservation(
            "NONEXISTENT", 10, "idempotency-key-1"
        )
        assert error is not None
        assert "not found" in error
        assert reservation is None

    def test_idempotent_reservation_retry(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)

        reservation1, _ = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )
        reservation2, _ = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )

        assert reservation1["id"] == reservation2["id"]

    def test_confirm_pending_reservation(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)
        reservation, _ = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )

        confirmed, error = service.confirm_reservation(reservation["id"])
        assert error is None
        assert confirmed["state"] == ReservationState.CONFIRMED

        # Verify order was created
        orders, total = service.get_orders()
        assert total == 1
        assert orders[0]["state"] == OrderState.CONFIRMED

    def test_confirm_expired_reservation(self, service, db):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)

        reservation, _ = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )

        # Manually expire the reservation in DB
        past = datetime.utcnow() - timedelta(minutes=1)
        db._connection().__enter__().execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past, reservation["id"]),
        )
        db._connection().__enter__().commit()

        confirmed, error = service.confirm_reservation(reservation["id"])
        assert error is not None
        assert "expired" in error
        assert confirmed is None

    def test_cancel_pending_reservation(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)
        reservation, _ = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )

        cancelled, error = service.cancel_reservation(reservation["id"])
        assert error is None
        assert cancelled["state"] == ReservationState.CANCELLED

    def test_cancel_confirmed_reservation_fails(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 100)
        reservation, _ = service.create_reservation(
            "WIDGET-001", 10, "idempotency-key-1"
        )
        service.confirm_reservation(reservation["id"])

        cancelled, error = service.cancel_reservation(reservation["id"])
        assert error is not None
        assert "Cannot cancel" in error


class TestOrders:
    def test_get_orders_empty(self, service):
        orders, total = service.get_orders()
        assert orders == []
        assert total == 0

    def test_get_orders_paginated(self, service):
        service.create_sku("WIDGET-001", "Premium Widget")
        service.adjust_stock("WIDGET-001", 1000)

        for i in range(25):
            reservation, _ = service.create_reservation(
                "WIDGET-001", 1, f"key-{i}"
            )
            service.confirm_reservation(reservation["id"])

        orders, total = service.get_orders(skip=0, limit=20)
        assert len(orders) == 20
        assert total == 25

        orders, total = service.get_orders(skip=20, limit=20)
        assert len(orders) == 5
