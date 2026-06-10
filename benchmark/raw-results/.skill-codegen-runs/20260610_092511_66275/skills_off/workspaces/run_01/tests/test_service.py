"""Unit tests for commerce service layer."""

import pytest
from datetime import datetime, timedelta

from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def repo():
    """Create an in-memory SQLite repository for testing."""
    repo = Repository("sqlite:///:memory:")
    repo.init_db()
    return repo


@pytest.fixture
def service(repo):
    """Create a service instance."""
    return CommerceService(repo)


class TestSKU:
    """Tests for SKU operations."""

    def test_create_sku(self, service):
        """Test creating a SKU."""
        sku = service.create_sku("SKU-001", 100)
        assert sku.sku_code == "SKU-001"
        assert sku.qty_on_hand == 100

    def test_create_duplicate_sku_fails(self, service):
        """Test that duplicate SKU codes are rejected."""
        service.create_sku("SKU-001", 100)
        with pytest.raises(ValueError, match="already exists"):
            service.create_sku("SKU-001", 50)

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        sku = service.create_sku("SKU-001", 100)
        adjusted = service.adjust_stock(sku.id, 50)
        assert adjusted.qty_on_hand == 150

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        sku = service.create_sku("SKU-001", 100)
        adjusted = service.adjust_stock(sku.id, -30)
        assert adjusted.qty_on_hand == 70

    def test_adjust_stock_insufficient(self, service):
        """Test that adjustment cannot go negative."""
        sku = service.create_sku("SKU-001", 50)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.adjust_stock(sku.id, -100)

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for nonexistent SKU."""
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock(999, 10)


class TestReservation:
    """Tests for reservation operations."""

    def test_create_reservation(self, service):
        """Test creating a reservation."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1", ttl_seconds=3600)
        assert res.sku_id == sku.id
        assert res.qty == 10
        assert res.status == "pending"

    def test_create_reservation_idempotent(self, service):
        """Test that same idempotency key returns same reservation."""
        sku = service.create_sku("SKU-001", 100)
        res1 = service.create_reservation(sku.id, 10, "idempotency-key-1")
        res2 = service.create_reservation(sku.id, 10, "idempotency-key-1")
        assert res1.id == res2.id

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails when insufficient stock."""
        sku = service.create_sku("SKU-001", 50)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation(sku.id, 100, "idempotency-key-1")

    def test_create_reservation_considers_pending(self, service):
        """Test that pending reservations reduce available stock."""
        sku = service.create_sku("SKU-001", 100)
        service.create_reservation(sku.id, 50, "res-1")
        # Second reservation should only see 50 available
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation(sku.id, 60, "res-2")

    def test_reservation_nonexistent_sku(self, service):
        """Test reservation fails for nonexistent SKU."""
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation(999, 10, "idempotency-key-1")

    def test_create_reservation_invalid_qty(self, service):
        """Test that zero or negative quantity is rejected."""
        sku = service.create_sku("SKU-001", 100)
        with pytest.raises(ValueError, match="must be positive"):
            service.create_reservation(sku.id, 0, "idempotency-key-1")

    def test_confirm_reservation(self, service):
        """Test confirming a reservation."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1")
        confirmed_res, order = service.confirm_reservation(res.id)
        assert confirmed_res.status == "confirmed"
        assert order.qty == 10

    def test_confirm_reservation_deducts_stock(self, service):
        """Test that confirming a reservation deducts from stock."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 30, "idempotency-key-1")
        service.confirm_reservation(res.id)
        updated_sku = service.repo.get_sku_by_id(sku.id)
        assert updated_sku.qty_on_hand == 70

    def test_confirm_expired_reservation(self, service):
        """Test that confirming expired reservation fails."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1", ttl_seconds=60)
        # Manually move the expiration back
        from sqlalchemy import update
        from commerce_service.models import ReservationModel

        with service.repo.get_session() as session:
            stmt = update(ReservationModel).where(ReservationModel.id == res.id).values(
                expires_at=datetime.utcnow() - timedelta(seconds=1)
            )
            session.execute(stmt)

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res.id)

    def test_confirm_already_confirmed_reservation(self, service):
        """Test confirming an already confirmed reservation."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1")
        service.confirm_reservation(res.id)
        # Confirming again should return the existing order
        confirmed_res, order = service.confirm_reservation(res.id)
        assert confirmed_res.status == "confirmed"
        assert order.id  # Should have an order ID

    def test_cancel_reservation(self, service):
        """Test cancelling a reservation."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1")
        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == "cancelled"

    def test_cancel_already_cancelled(self, service):
        """Test cancelling an already cancelled reservation."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1")
        service.cancel_reservation(res.id)
        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == "cancelled"

    def test_cancel_confirmed_fails(self, service):
        """Test that cancelling confirmed reservation fails."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1")
        service.confirm_reservation(res.id)
        with pytest.raises(ValueError, match="Cannot cancel"):
            service.cancel_reservation(res.id)


class TestOrder:
    """Tests for order operations."""

    def test_get_order(self, service):
        """Test retrieving an order."""
        sku = service.create_sku("SKU-001", 100)
        res = service.create_reservation(sku.id, 10, "idempotency-key-1")
        _, order = service.confirm_reservation(res.id)
        retrieved = service.get_order(order.id)
        assert retrieved.id == order.id
        assert retrieved.qty == 10

    def test_list_orders(self, service):
        """Test listing orders with pagination."""
        sku = service.create_sku("SKU-001", 100)
        for i in range(5):
            res = service.create_reservation(sku.id, 5, f"idempotency-key-{i}")
            service.confirm_reservation(res.id)

        orders, total = service.list_orders(offset=0, limit=3)
        assert len(orders) == 3
        assert total == 5

    def test_list_orders_pagination(self, service):
        """Test order list pagination."""
        sku = service.create_sku("SKU-001", 100)
        for i in range(10):
            res = service.create_reservation(sku.id, 2, f"idempotency-key-{i}")
            service.confirm_reservation(res.id)

        page1, total = service.list_orders(offset=0, limit=5)
        page2, _ = service.list_orders(offset=5, limit=5)

        assert len(page1) == 5
        assert len(page2) == 5
        assert total == 10
        assert page1[0].id != page2[0].id
