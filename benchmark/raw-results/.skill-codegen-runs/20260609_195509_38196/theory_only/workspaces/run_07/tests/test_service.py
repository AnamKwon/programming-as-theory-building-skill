"""Tests for service layer business logic."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from commerce_service.models import Base
from commerce_service.service import InventoryService


@pytest.fixture
def db():
    """In-memory SQLite database for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class TestInventoryService:
    """Test inventory reservation and order logic."""

    def test_create_sku(self, db):
        """Creating a SKU initializes with available stock."""
        svc = InventoryService(db)
        sku = svc.create_sku("WIDGET-001", 100)
        assert sku.sku == "WIDGET-001"
        assert sku.available == 100
        assert sku.reserved == 0

    def test_create_duplicate_sku_raises(self, db):
        """Creating a duplicate SKU raises ValueError."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        with pytest.raises(ValueError, match="already exists"):
            svc.create_sku("WIDGET-001", 50)

    def test_adjust_stock_positive(self, db):
        """Positive stock adjustment increases available."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        svc.adjust_stock("WIDGET-001", 50, "restock")
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 150

    def test_adjust_stock_negative(self, db):
        """Negative stock adjustment decreases available."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        svc.adjust_stock("WIDGET-001", -30, "damage")
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 70

    def test_adjust_stock_below_zero_raises(self, db):
        """Adjustment that would go negative raises ValueError."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        with pytest.raises(ValueError, match="negative"):
            svc.adjust_stock("WIDGET-001", -150, "error")

    def test_reserve_inventory_success(self, db):
        """Successful reservation deducts from available."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        assert reservation.status == "pending"
        assert reservation.quantity == 30
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 70  # Deducted
        assert sku.reserved == 0    # Not yet confirmed

    def test_reserve_inventory_insufficient_stock(self, db):
        """Reserving more than available stock raises ValueError."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        with pytest.raises(ValueError, match="Insufficient available"):
            svc.reserve_inventory("WIDGET-001", 150, "idempotency-key-1")

    def test_reserve_inventory_unknown_sku(self, db):
        """Reserving unknown SKU raises ValueError."""
        svc = InventoryService(db)
        with pytest.raises(ValueError, match="not found"):
            svc.reserve_inventory("UNKNOWN", 10, "idempotency-key-1")

    def test_reserve_inventory_idempotent(self, db):
        """Retrying with same idempotency key returns same reservation."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        res1 = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        res2 = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        assert res1.id == res2.id
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 70  # Only deducted once

    def test_confirm_reservation_success(self, db):
        """Confirming a reservation moves stock to reserved and creates order."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        reservation, order = svc.confirm_reservation(reservation.id)
        assert reservation.status == "confirmed"
        assert order.status == "confirmed"
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 70  # Still deducted
        assert sku.reserved == 30   # Now reserved

    def test_confirm_non_pending_reservation_raises(self, db):
        """Confirming a non-pending reservation raises ValueError."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        svc.confirm_reservation(reservation.id)
        with pytest.raises(ValueError, match="Cannot confirm"):
            svc.confirm_reservation(reservation.id)

    def test_confirm_expired_reservation_raises(self, db):
        """Confirming an expired reservation raises ValueError."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        # Manually expire the reservation
        from datetime import datetime
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.flush()
        with pytest.raises(ValueError, match="expired"):
            svc.confirm_reservation(reservation.id)

    def test_cancel_pending_reservation(self, db):
        """Cancelling a pending reservation restores available stock."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        svc.cancel_reservation(reservation.id)
        reservation = svc.reservation.get_reservation(reservation.id)
        assert reservation.status == "cancelled"
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 100  # Restored

    def test_cancel_confirmed_reservation(self, db):
        """Cancelling a confirmed reservation moves stock back to available."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        svc.confirm_reservation(reservation.id)
        svc.cancel_reservation(reservation.id)
        reservation = svc.reservation.get_reservation(reservation.id)
        assert reservation.status == "cancelled"
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 100  # Restored
        assert sku.reserved == 0

    def test_expire_pending_reservations(self, db):
        """Expiring pending reservations restores stock and marks as expired."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        reservation = svc.reserve_inventory("WIDGET-001", 30, "idempotency-key-1")
        # Manually expire the reservation
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.flush()
        count = svc.expire_pending_reservations()
        assert count == 1
        reservation = svc.reservation.get_reservation(reservation.id)
        assert reservation.status == "expired"
        sku = svc.inventory.get_sku("WIDGET-001")
        assert sku.available == 100  # Restored

    def test_list_orders_pagination(self, db):
        """Listing orders respects pagination."""
        svc = InventoryService(db)
        svc.create_sku("WIDGET-001", 100)
        # Create multiple orders
        for i in range(5):
            res = svc.reserve_inventory("WIDGET-001", 10, f"key-{i}")
            svc.confirm_reservation(res.id)
        orders, total = svc.list_orders(page=1, page_size=2)
        assert len(orders) == 2
        assert total == 5
        orders, total = svc.list_orders(page=2, page_size=2)
        assert len(orders) == 2
        orders, total = svc.list_orders(page=3, page_size=2)
        assert len(orders) == 1
