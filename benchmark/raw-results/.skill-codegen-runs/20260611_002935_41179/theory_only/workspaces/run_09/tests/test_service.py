import pytest
import time
from datetime import datetime, timezone, timedelta
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def repo():
    """Create a fresh repository for each test."""
    r = Repository(":memory:")
    yield r


@pytest.fixture
def service(repo):
    """Create a service with the test repository."""
    return CommerceService(repo)


class TestSkuManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", 100)
        assert result["sku"] == "SKU001"
        assert result["initial_stock"] == 100

    def test_adjust_stock(self, service):
        service.create_sku("SKU001", 100)
        new_stock = service.adjust_stock("SKU001", 50)
        assert new_stock == 150

        new_stock = service.adjust_stock("SKU001", -30)
        assert new_stock == 120


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU001", 100)
        result, status = service.create_reservation("SKU001", 50, "key123")
        assert status == 201
        assert result["status"] == "PENDING"
        assert result["quantity"] == 50
        assert result["sku"] == "SKU001"

    def test_insufficient_stock(self, service):
        service.create_sku("SKU001", 30)
        result, status = service.create_reservation("SKU001", 50, "key123")
        assert status == 400
        assert result["detail"] == "Insufficient stock"

    def test_idempotent_reservation(self, service):
        service.create_sku("SKU001", 100)

        # First reservation
        result1, status1 = service.create_reservation("SKU001", 50, "key123")
        assert status1 == 201

        # Second reservation with same key
        result2, status2 = service.create_reservation("SKU001", 50, "key123")
        assert status2 == 201
        assert result1["id"] == result2["id"]

        # Stock should only be deducted once
        sku_data = service.repo.get_sku_by_name("SKU001")
        assert sku_data["stock"] == 50  # 100 - 50


class TestConfirmation:
    def test_confirm_reservation(self, service):
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "key123")
        reservation_id = res["id"]

        result, status = service.confirm_reservation(reservation_id)
        assert status == 200
        assert result["status"] == "CONFIRMED"
        assert result["order_id"] > 0

    def test_confirm_non_pending_fails(self, service):
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "key123")
        reservation_id = res["id"]

        service.confirm_reservation(reservation_id)

        # Try to confirm again
        result, status = service.confirm_reservation(reservation_id)
        assert status == 400
        assert "not in PENDING state" in result["detail"]

    def test_expired_reservation_fails(self, service, repo):
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "key123")
        reservation_id = res["id"]

        # Manually set created_at to 301 seconds ago
        reservation = repo.get_reservation(reservation_id)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        conn = repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation_id)
        )
        conn.commit()
        repo._close_conn(conn)

        # Try to confirm
        result, status = service.confirm_reservation(reservation_id)
        assert status == 400
        assert result["detail"] == "Reservation expired"

        # Stock should be restored
        sku_data = repo.get_sku_by_name("SKU001")
        assert sku_data["stock"] == 100

        # Reservation should be marked expired
        updated = repo.get_reservation(reservation_id)
        assert updated["status"] == "EXPIRED"


class TestCancellation:
    def test_cancel_reservation(self, service):
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "key123")
        reservation_id = res["id"]

        result, status = service.cancel_reservation(reservation_id)
        assert status == 200
        assert result["status"] == "CANCELLED"
        assert result["stock_restored"] == 50

        # Verify stock is restored
        sku_data = service.repo.get_sku_by_name("SKU001")
        assert sku_data["stock"] == 100

    def test_cancel_non_pending_fails(self, service):
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "key123")
        reservation_id = res["id"]

        service.confirm_reservation(reservation_id)

        result, status = service.cancel_reservation(reservation_id)
        assert status == 400
        assert "not in PENDING state" in result["detail"]


class TestOrders:
    def test_get_orders_paginated(self, service):
        service.create_sku("SKU001", 1000)

        # Create multiple reservations and confirm them
        for i in range(15):
            res, _ = service.create_reservation("SKU001", 10, f"key{i}")
            service.confirm_reservation(res["id"])

        # Get first page
        result = service.get_orders_paginated(1, 10)
        assert len(result["items"]) == 10
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 15

        # Get second page
        result = service.get_orders_paginated(2, 10)
        assert len(result["items"]) == 5
        assert result["page"] == 2
        assert result["total"] == 15
