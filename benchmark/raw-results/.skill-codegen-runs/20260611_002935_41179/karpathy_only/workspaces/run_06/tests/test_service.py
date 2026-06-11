import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def repo():
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    return Service(repo)


class TestSKU:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", 100)
        assert result["sku"] == "SKU001"
        assert result["stock"] == 100

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("SKU001", 100)
        with pytest.raises(HTTPException) as exc_info:
            service.create_sku("SKU001", 50)
        assert exc_info.value.status_code == 400


class TestStock:
    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["stock"] == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["stock"] == 70

    def test_adjust_nonexistent_sku_fails(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("NONEXISTENT", 10)
        assert exc_info.value.status_code == 404


class TestReservation:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        result = service.create_reservation("SKU001", 30, "key1")
        assert result.sku == "SKU001"
        assert result.quantity == 30
        assert result.status == "PENDING"
        assert result.idempotency_key == "key1"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", 100)
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("SKU001", 150, "key1")
        assert exc_info.value.status_code == 400
        assert "Insufficient stock" in exc_info.value.detail

    def test_create_reservation_reduces_stock(self, service):
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "key1")
        stock = service.repo.get_sku_stock("SKU001")
        assert stock == 70

    def test_idempotent_reservation_retry(self, service):
        service.create_sku("SKU001", 100)
        result1 = service.create_reservation("SKU001", 30, "key1")
        result2 = service.create_reservation("SKU001", 30, "key1")
        assert result1.id == result2.id
        assert result1.idempotency_key == result2.idempotency_key
        stock = service.repo.get_sku_stock("SKU001")
        assert stock == 70  # Only deducted once

    def test_idempotent_different_quantities_same_key_returns_first(self, service):
        service.create_sku("SKU001", 1000)
        result1 = service.create_reservation("SKU001", 30, "key1")
        result2 = service.create_reservation("SKU001", 999, "key1")
        assert result1.id == result2.id
        assert result2.quantity == 30  # Returns the first one


class TestConfirmation:
    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key1")
        result = service.confirm_reservation(res.id)
        assert result.reservation_id == res.id
        assert result.sku == "SKU001"
        assert result.quantity == 30
        assert result.order_id is not None

    def test_confirm_nonpending_fails(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key1")
        service.confirm_reservation(res.id)
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res.id)
        assert exc_info.value.status_code == 400
        assert "not pending" in exc_info.value.detail

    def test_confirm_expired_reservation_fails(self, service, repo):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key1")
        # Manually update timestamp to be more than 300 seconds old
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        conn = repo._get_connection()
        cursor = conn.__enter__().cursor()
        cursor.execute(
            "UPDATE reservations SET timestamp = ? WHERE id = ?",
            (old_time, res.id),
        )
        conn.__exit__(None, None, None)

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res.id)
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail

        # Check that status was changed to EXPIRED and stock was restored
        reservation = service.repo.get_reservation(res.id)
        assert reservation["status"] == "EXPIRED"
        stock = service.repo.get_sku_stock("SKU001")
        assert stock == 100


class TestCancellation:
    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key1")
        result = service.cancel_reservation(res.id)
        assert result["status"] == "CANCELLED"
        assert result["stock_restored"] == 30
        stock = service.repo.get_sku_stock("SKU001")
        assert stock == 100

    def test_cancel_nonpending_fails(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "key1")
        service.confirm_reservation(res.id)
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(res.id)
        assert exc_info.value.status_code == 400
        assert "not pending" in exc_info.value.detail


class TestOrderListing:
    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["size"] == 10

    def test_list_orders_with_pagination(self, service):
        service.create_sku("SKU001", 1000)
        for i in range(25):
            res = service.create_reservation("SKU001", 10, f"key{i}")
            service.confirm_reservation(res.id)

        page1 = service.list_orders(page=1, size=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 25
        assert page1["page"] == 1

        page2 = service.list_orders(page=2, size=10)
        assert len(page2["items"]) == 10
        assert page2["page"] == 2

        page3 = service.list_orders(page=3, size=10)
        assert len(page3["items"]) == 5
        assert page3["page"] == 3
