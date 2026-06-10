"""Tests for the service layer."""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def session():
    db = Database("sqlite:///:memory:")
    session = db.get_session()
    yield session
    session.close()


@pytest.fixture
def service(session):
    return CommerceService(session)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("PRODUCT-001", 100)
        assert result["sku"] == "PRODUCT-001"
        assert result["initial_stock"] == 100
        assert result["available_stock"] == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku("PRODUCT-001", 100)
        result = service.adjust_stock("PRODUCT-001", 50)
        assert result["available_stock"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("PRODUCT-001", 100)
        result = service.adjust_stock("PRODUCT-001", -30)
        assert result["available_stock"] == 70

    def test_adjust_stock_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("PRODUCT-001", 100)
        result, status = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        assert status == 201
        assert result["sku"] == "PRODUCT-001"
        assert result["quantity"] == 25
        assert result["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("PRODUCT-001", 100)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("PRODUCT-001", 150, "idem-key-1")

    def test_idempotency_returns_existing(self, service):
        service.create_sku("PRODUCT-001", 100)
        result1, status1 = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        result2, status2 = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        assert result1["id"] == result2["id"]
        assert result1["sku"] == result2["sku"]

    def test_idempotency_does_not_double_deduct(self, service):
        service.create_sku("PRODUCT-001", 100)
        service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        # Check stock was only deducted once
        sku = service.sku_repo.get_sku("PRODUCT-001")
        assert sku.available_stock == 75

    def test_confirm_reservation_success(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        result = service.confirm_reservation(res["id"])
        assert result["status"] == "CONFIRMED"
        assert "order_id" in result

    def test_confirm_reservation_expired(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        # Manually set created_at to be old
        reservation = service.reservation_repo.get_reservation(res["id"])
        old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        reservation.created_at = old_time
        service.session.commit()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res["id"])

    def test_confirm_expired_restores_stock(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        # Manually set created_at to be old
        reservation = service.reservation_repo.get_reservation(res["id"])
        old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        reservation.created_at = old_time
        service.session.commit()

        try:
            service.confirm_reservation(res["id"])
        except ValueError:
            pass

        sku = service.sku_repo.get_sku("PRODUCT-001")
        assert sku.available_stock == 100

    def test_confirm_non_pending_fails(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        service.confirm_reservation(res["id"])
        with pytest.raises(ValueError, match="Cannot confirm"):
            service.confirm_reservation(res["id"])

    def test_cancel_reservation_success(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        result = service.cancel_reservation(res["id"])
        assert result["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        service.cancel_reservation(res["id"])
        sku = service.sku_repo.get_sku("PRODUCT-001")
        assert sku.available_stock == 100

    def test_cancel_non_pending_fails(self, service):
        service.create_sku("PRODUCT-001", 100)
        res, _ = service.create_reservation("PRODUCT-001", 25, "idem-key-1")
        service.confirm_reservation(res["id"])
        with pytest.raises(ValueError, match="Cannot cancel"):
            service.cancel_reservation(res["id"])


class TestOrders:
    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1

    def test_list_orders_pagination(self, service):
        service.create_sku("PRODUCT-001", 1000)
        for i in range(15):
            res, _ = service.create_reservation("PRODUCT-001", 10, f"idem-key-{i}")
            service.confirm_reservation(res["id"])

        page1 = service.list_orders(page=1, size=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 15

        page2 = service.list_orders(page=2, size=10)
        assert len(page2["items"]) == 5
        assert page2["total"] == 15

    def test_list_orders_page_offset(self, service):
        service.create_sku("PRODUCT-001", 1000)
        for i in range(5):
            res, _ = service.create_reservation("PRODUCT-001", 10, f"idem-key-{i}")
            service.confirm_reservation(res["id"])

        page1_ids = [o["id"] for o in service.list_orders(page=1, size=2)["items"]]
        page2_ids = [o["id"] for o in service.list_orders(page=2, size=2)["items"]]

        assert page1_ids != page2_ids
        assert len(set(page1_ids) & set(page2_ids)) == 0
