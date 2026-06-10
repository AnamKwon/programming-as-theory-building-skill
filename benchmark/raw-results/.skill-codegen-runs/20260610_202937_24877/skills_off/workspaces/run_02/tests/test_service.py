import pytest
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from src.commerce_service.service import CommerceService
from src.commerce_service.repository import init_db, get_db_connection, DB_PATH


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and cleanup for each test."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest.fixture
def service():
    return CommerceService()


class TestSKUService:
    def test_create_sku(self, service):
        result = service.create_sku("ABC123", 100)
        assert result.sku == "ABC123"
        assert result.stock == 100
        assert result.id is not None

    def test_adjust_stock_positive(self, service):
        service.create_sku("ABC123", 100)
        result = service.adjust_stock("ABC123", 50)
        assert result.stock == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("ABC123", 100)
        result = service.adjust_stock("ABC123", -30)
        assert result.stock == 70


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("ABC123", 100)
        response, status_code = service.create_reservation("ABC123", 10, "key-1")
        assert status_code == 201
        assert response.sku == "ABC123"
        assert response.quantity == 10
        assert response.status == "PENDING"
        assert response.idempotency_key == "key-1"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("ABC123", 50)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("ABC123", 100, "key-1")

    def test_create_reservation_idempotency(self, service):
        service.create_sku("ABC123", 100)
        response1, status1 = service.create_reservation("ABC123", 10, "key-1")
        response2, status2 = service.create_reservation("ABC123", 10, "key-1")

        assert status1 == 201
        assert status2 == 200
        assert response1.id == response2.id
        assert response1.idempotency_key == response2.idempotency_key

    def test_idempotency_no_double_deduction(self, service):
        service.create_sku("ABC123", 100)
        service.create_reservation("ABC123", 10, "key-1")
        service.create_reservation("ABC123", 10, "key-1")

        # Stock should only be deducted once
        stock = service.sku_repo.get_stock("ABC123")
        assert stock == 90

    def test_confirm_pending_reservation(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")
        confirmed = service.confirm_reservation(res.id)
        assert confirmed.status == "CONFIRMED"

    def test_confirm_nonpending_reservation_fails(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")
        service.confirm_reservation(res.id)
        with pytest.raises(ValueError, match="not in PENDING state"):
            service.confirm_reservation(res.id)

    def test_cancel_pending_reservation(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")
        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == "CANCELLED"

    def test_cancel_restores_stock(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")
        service.cancel_reservation(res.id)
        stock = service.sku_repo.get_stock("ABC123")
        assert stock == 100

    def test_cancel_nonpending_reservation_fails(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")
        service.confirm_reservation(res.id)
        with pytest.raises(ValueError, match="not in PENDING state"):
            service.cancel_reservation(res.id)

    def test_expired_reservation_on_confirm(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")

        # Manually update the created_at to be older than TTL
        conn = get_db_connection()
        cursor = conn.cursor()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res.id)
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res.id)

    def test_expired_reservation_restores_stock(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")

        # Manually update the created_at to be older than TTL
        conn = get_db_connection()
        cursor = conn.cursor()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res.id)
        )
        conn.commit()
        conn.close()

        try:
            service.confirm_reservation(res.id)
        except ValueError:
            pass

        stock = service.sku_repo.get_stock("ABC123")
        assert stock == 100


class TestOrder:
    def test_confirm_creates_order(self, service):
        service.create_sku("ABC123", 100)
        res, _ = service.create_reservation("ABC123", 10, "key-1")
        service.confirm_reservation(res.id)
        orders, total = service.order_repo.get_orders_paginated(1, 10)
        assert len(orders) == 1
        assert orders[0]["reservation_id"] == res.id
        assert total == 1

    def test_get_orders_pagination(self, service):
        service.create_sku("ABC123", 100)
        for i in range(25):
            res, _ = service.create_reservation("ABC123", 1, f"key-{i}")
            service.confirm_reservation(res.id)

        page1 = service.get_orders_paginated(1, 10)
        assert len(page1.items) == 10
        assert page1.page == 1
        assert page1.size == 10
        assert page1.total == 25

        page2 = service.get_orders_paginated(2, 10)
        assert len(page2.items) == 10

        page3 = service.get_orders_paginated(3, 10)
        assert len(page3.items) == 5
