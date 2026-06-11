"""Tests for the service layer."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from commerce_service.repository import init_db, DB_PATH
from commerce_service.service import SKUService, ReservationService, OrderService


@pytest.fixture(autouse=True)
def setup_db():
    """Set up a clean database for each test."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    yield
    if DB_PATH.exists():
        DB_PATH.unlink()


class TestSKUService:
    """Tests for SKU operations."""

    def test_create_sku(self):
        """Test creating a new SKU."""
        service = SKUService()
        result = service.create_sku("SKU-001", 100)
        assert result["sku"] == "SKU-001"
        assert result["available_stock"] == 100

    def test_adjust_stock_positive(self):
        """Test increasing stock."""
        service = SKUService()
        service.create_sku("SKU-002", 50)
        result = service.adjust_stock("SKU-002", 20)
        assert result["available_stock"] == 70

    def test_adjust_stock_negative(self):
        """Test decreasing stock."""
        service = SKUService()
        service.create_sku("SKU-003", 50)
        result = service.adjust_stock("SKU-003", -10)
        assert result["available_stock"] == 40

    def test_get_available_stock(self):
        """Test retrieving available stock."""
        service = SKUService()
        service.create_sku("SKU-004", 75)
        stock = service.get_available_stock("SKU-004")
        assert stock == 75


class TestReservationService:
    """Tests for reservation operations."""

    def test_create_reservation_success(self):
        """Test successful reservation creation."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-005", 100)
        result, status_code = reservation_service.create_reservation(
            "SKU-005", 30, "idempotency-key-1"
        )

        assert status_code == 201
        assert result["id"] == 1
        assert result["sku"] == "SKU-005"
        assert result["quantity"] == 30
        assert result["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self):
        """Test reservation creation with insufficient stock."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-006", 20)
        result, status_code = reservation_service.create_reservation(
            "SKU-006", 50, "idempotency-key-2"
        )

        assert status_code == 400
        assert result["detail"] == "Insufficient stock"

    def test_idempotent_reservation(self):
        """Test that idempotent retry returns same data without double-deduction."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-007", 100)

        result1, status1 = reservation_service.create_reservation(
            "SKU-007", 30, "idempotency-key-3"
        )
        result2, status2 = reservation_service.create_reservation(
            "SKU-007", 30, "idempotency-key-3"
        )

        assert result1 == result2
        assert result1["id"] == result2["id"]

        stock = sku_service.get_available_stock("SKU-007")
        assert stock == 70

    def test_confirm_reservation_success(self):
        """Test successful reservation confirmation."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-008", 100)
        res_result, _ = reservation_service.create_reservation(
            "SKU-008", 30, "idempotency-key-4"
        )

        order_result, status_code = reservation_service.confirm_reservation(
            res_result["id"]
        )

        assert status_code == 200
        assert order_result["id"] == 1
        assert order_result["reservation_id"] == res_result["id"]

    def test_confirm_reservation_expired(self):
        """Test that confirming an expired reservation fails and restores stock."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-009", 100)
        res_result, _ = reservation_service.create_reservation(
            "SKU-009", 30, "idempotency-key-5"
        )

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        old_time = (
            datetime.utcnow() - timedelta(seconds=310)
        ).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res_result["id"]),
        )
        conn.commit()
        conn.close()

        result, status_code = reservation_service.confirm_reservation(
            res_result["id"]
        )

        assert status_code == 400
        assert result["detail"] == "Reservation expired"

        stock = sku_service.get_available_stock("SKU-009")
        assert stock == 100

    def test_confirm_non_pending_reservation(self):
        """Test that confirming a non-PENDING reservation fails."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-010", 100)
        res_result, _ = reservation_service.create_reservation(
            "SKU-010", 30, "idempotency-key-6"
        )

        reservation_service.confirm_reservation(res_result["id"])

        result, status_code = reservation_service.confirm_reservation(
            res_result["id"]
        )

        assert status_code == 400
        assert result["detail"] == "Reservation is not in PENDING status"

    def test_cancel_reservation_success(self):
        """Test successful reservation cancellation."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-011", 100)
        res_result, _ = reservation_service.create_reservation(
            "SKU-011", 30, "idempotency-key-7"
        )

        stock_before = sku_service.get_available_stock("SKU-011")
        assert stock_before == 70

        cancel_result, status_code = reservation_service.cancel_reservation(
            res_result["id"]
        )

        assert status_code == 200
        assert cancel_result["status"] == "CANCELLED"

        stock_after = sku_service.get_available_stock("SKU-011")
        assert stock_after == 100

    def test_cancel_non_pending_reservation(self):
        """Test that cancelling a non-PENDING reservation fails."""
        sku_service = SKUService()
        reservation_service = ReservationService()

        sku_service.create_sku("SKU-012", 100)
        res_result, _ = reservation_service.create_reservation(
            "SKU-012", 30, "idempotency-key-8"
        )

        reservation_service.confirm_reservation(res_result["id"])

        result, status_code = reservation_service.cancel_reservation(
            res_result["id"]
        )

        assert status_code == 400
        assert result["detail"] == "Reservation is not in PENDING status"


class TestOrderService:
    """Tests for order operations."""

    def test_get_orders_empty(self):
        """Test getting orders when none exist."""
        service = OrderService()
        result = service.get_orders()

        assert result["total"] == 0
        assert result["orders"] == []
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total_pages"] == 0

    def test_get_orders_pagination(self):
        """Test pagination of orders."""
        sku_service = SKUService()
        reservation_service = ReservationService()
        order_service = OrderService()

        sku_service.create_sku("SKU-013", 1000)

        for i in range(15):
            res_result, _ = reservation_service.create_reservation(
                "SKU-013", 10, f"idempotency-key-{i}"
            )
            reservation_service.confirm_reservation(res_result["id"])

        result_page1 = order_service.get_orders(page=1, size=10)
        assert len(result_page1["orders"]) == 10
        assert result_page1["total"] == 15
        assert result_page1["total_pages"] == 2

        result_page2 = order_service.get_orders(page=2, size=10)
        assert len(result_page2["orders"]) == 5
        assert result_page2["page"] == 2
