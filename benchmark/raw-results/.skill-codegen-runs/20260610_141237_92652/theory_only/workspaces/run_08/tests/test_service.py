import pytest
import time
from datetime import datetime, timedelta
from src.commerce_service.repository import Repository
from src.commerce_service.service import Service


@pytest.fixture
def repository():
    return Repository(":memory:")


@pytest.fixture
def service(repository):
    return Service(repository)


class TestSkuOperations:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", 100)
        assert result["sku"] == "SKU001"
        assert result["available_stock"] == 100
        assert "id" in result

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU002", 100)
        result = service.adjust_stock("SKU002", 50)
        assert result["available_stock"] == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU003", 100)
        result = service.adjust_stock("SKU003", -30)
        assert result["available_stock"] == 70

    def test_adjust_stock_nonexistent(self, service):
        result = service.adjust_stock("NONEXISTENT", 10)
        assert result is None


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU004", 100)
        result = service.create_reservation("SKU004", 10, "key-001")
        assert result["sku"] == "SKU004"
        assert result["quantity"] == 10
        assert result["status"] == "PENDING"
        assert "id" in result
        assert "created_at" in result

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU005", 5)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU005", 10, "key-002")

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation("NONEXISTENT", 10, "key-003")

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU006", 100)
        # Create first reservation
        result1 = service.create_reservation("SKU006", 10, "key-004")
        # Create with same idempotency key
        result2 = service.create_reservation("SKU006", 10, "key-004")
        # Should return the same reservation
        assert result1["id"] == result2["id"]
        assert result1["created_at"] == result2["created_at"]

    def test_stock_deduction_on_reservation(self, service, repository):
        service.create_sku("SKU007", 100)
        service.create_reservation("SKU007", 10, "key-005")
        # Verify stock was deducted
        sku_info = repository.get_sku_by_sku("SKU007")
        assert sku_info["available_stock"] == 90

    def test_stock_not_deducted_twice_on_idempotent_retry(self, service, repository):
        service.create_sku("SKU008", 100)
        service.create_reservation("SKU008", 10, "key-006")
        service.create_reservation("SKU008", 10, "key-006")  # Retry
        # Stock should only be deducted once
        sku_info = repository.get_sku_by_sku("SKU008")
        assert sku_info["available_stock"] == 90


class TestReservationConfirmation:
    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU009", 100)
        res = service.create_reservation("SKU009", 10, "key-007")
        order = service.confirm_reservation(res["id"])
        assert order["sku"] == "SKU009"
        assert order["quantity"] == 10
        assert "reservation_id" in order

    def test_confirm_non_existent_reservation(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.confirm_reservation(999)

    def test_confirm_non_pending_reservation(self, service):
        service.create_sku("SKU010", 100)
        res = service.create_reservation("SKU010", 10, "key-008")
        service.confirm_reservation(res["id"])
        # Try to confirm again
        with pytest.raises(ValueError, match="not in PENDING state"):
            service.confirm_reservation(res["id"])

    def test_confirm_expired_reservation(self, service, repository):
        service.create_sku("SKU011", 100)
        res = service.create_reservation("SKU011", 10, "key-009")

        # Manually set created_at to 301 seconds ago
        reservation_id = res["id"]
        conn = repository._get_connection()
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation_id)
        )
        conn.commit()
        conn.close()

        # Try to confirm
        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(reservation_id)

        # Verify status was set to EXPIRED
        updated = repository.get_reservation_by_id(reservation_id)
        assert updated["status"] == "EXPIRED"

        # Verify stock was restored
        sku_info = repository.get_sku_by_sku("SKU011")
        assert sku_info["available_stock"] == 100


class TestReservationCancellation:
    def test_cancel_reservation_success(self, service, repository):
        service.create_sku("SKU012", 100)
        res = service.create_reservation("SKU012", 10, "key-010")
        cancelled = service.cancel_reservation(res["id"])
        assert cancelled["status"] == "CANCELLED"
        # Verify stock was restored
        sku_info = repository.get_sku_by_sku("SKU012")
        assert sku_info["available_stock"] == 100

    def test_cancel_non_existent_reservation(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.cancel_reservation(999)

    def test_cancel_non_pending_reservation(self, service):
        service.create_sku("SKU013", 100)
        res = service.create_reservation("SKU013", 10, "key-011")
        service.confirm_reservation(res["id"])
        # Try to cancel confirmed reservation
        with pytest.raises(ValueError, match="not in PENDING state"):
            service.cancel_reservation(res["id"])


class TestOrders:
    def test_get_orders_pagination(self, service):
        service.create_sku("SKU014", 1000)
        # Create multiple orders
        for i in range(15):
            res = service.create_reservation("SKU014", 10, f"key-{i}")
            service.confirm_reservation(res["id"])

        # Get first page
        orders, total = service.get_orders(page=1, size=10)
        assert len(orders) == 10
        assert total == 15

        # Get second page
        orders, total = service.get_orders(page=2, size=10)
        assert len(orders) == 5
        assert total == 15

    def test_get_orders_empty(self, service):
        service.create_sku("SKU015", 100)
        orders, total = service.get_orders(page=1, size=10)
        assert len(orders) == 0
        assert total == 0
