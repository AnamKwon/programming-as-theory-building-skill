"""Tests for the service layer."""

import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import ReservationStatus


@pytest.fixture
def repo():
    """Create an in-memory SQLite repository for testing."""
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    """Create a service instance with test repository."""
    return CommerceService(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        sku = service.create_sku("sku-001", "Widget")
        assert sku.id == "sku-001"
        assert sku.name == "Widget"

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("sku-001", "Widget")
        with pytest.raises(ValueError, match="already exists"):
            service.create_sku("sku-001", "Another")


class TestStockAdjustment:
    def test_adjust_stock(self, service):
        service.create_sku("sku-001", "Widget")
        stock = service.adjust_stock("sku-001", 100)
        assert stock.quantity == 100

    def test_adjust_stock_negative(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 100)
        stock = service.adjust_stock("sku-001", -30)
        assert stock.quantity == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="does not exist"):
            service.adjust_stock("sku-001", 100)

    def test_adjust_stock_zero_delta_fails(self, service):
        service.create_sku("sku-001", "Widget")
        with pytest.raises(ValueError, match="cannot be zero"):
            service.adjust_stock("sku-001", 0)


class TestReservations:
    def test_create_reservation(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        reservation = service.create_reservation("sku-001", 5)
        assert reservation.sku_id == "sku-001"
        assert reservation.quantity == 5
        assert reservation.status == ReservationStatus.PENDING

    def test_reservation_insufficient_stock(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 3)

        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("sku-001", 5)

    def test_reservation_idempotency(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        res1 = service.create_reservation("sku-001", 5, idempotency_key="key-001")
        res2 = service.create_reservation("sku-001", 5, idempotency_key="key-001")

        assert res1.id == res2.id

    def test_cancel_reservation(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        reservation = service.create_reservation("sku-001", 5)
        cancelled = service.cancel_reservation(reservation.id)

        assert cancelled.status == ReservationStatus.CANCELLED

    def test_cancel_non_pending_fails(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        reservation = service.create_reservation("sku-001", 5)
        service.confirm_reservation(reservation.id)

        with pytest.raises(ValueError, match="Can only cancel pending"):
            service.cancel_reservation(reservation.id)


class TestOrders:
    def test_confirm_reservation(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        reservation = service.create_reservation("sku-001", 5)
        order = service.confirm_reservation(reservation.id)

        assert order.reservation_id == reservation.id
        assert order.quantity == 5
        assert order.status.value == "reserved"

    def test_confirm_reservation_insufficient_stock(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        res1 = service.create_reservation("sku-001", 8)
        service.confirm_reservation(res1.id)

        res2 = service.create_reservation("sku-001", 5)
        with pytest.raises(ValueError, match="Stock no longer available"):
            service.confirm_reservation(res2.id)

    def test_confirm_expired_reservation_fails(self, service, repo):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 10)

        # Create reservation
        reservation = service.create_reservation("sku-001", 5)

        # Manually expire it
        session = repo.get_session()
        session.query(service.repo.ReservationModel).filter_by(id=reservation.id).update({
            service.repo.ReservationModel.expires_at: datetime.utcnow() - timedelta(minutes=1)
        })
        session.commit()
        session.close()

        # Cleanup and verify it's marked expired
        service.repo.cleanup_expired_reservations(session)

        with pytest.raises(ValueError, match="has expired"):
            service.confirm_reservation(reservation.id)

    def test_list_orders(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 100)

        res1 = service.create_reservation("sku-001", 10)
        service.confirm_reservation(res1.id)

        res2 = service.create_reservation("sku-001", 20)
        service.confirm_reservation(res2.id)

        result = service.list_orders(page=1, page_size=10)
        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["page"] == 1
        assert result["total_pages"] == 1

    def test_list_orders_pagination(self, service):
        service.create_sku("sku-001", "Widget")
        service.adjust_stock("sku-001", 1000)

        for i in range(25):
            res = service.create_reservation("sku-001", 10)
            service.confirm_reservation(res.id)

        result1 = service.list_orders(page=1, page_size=10)
        result2 = service.list_orders(page=2, page_size=10)
        result3 = service.list_orders(page=3, page_size=10)

        assert result1["total"] == 25
        assert len(result1["items"]) == 10
        assert len(result2["items"]) == 10
        assert len(result3["items"]) == 5
        assert result1["total_pages"] == 3
