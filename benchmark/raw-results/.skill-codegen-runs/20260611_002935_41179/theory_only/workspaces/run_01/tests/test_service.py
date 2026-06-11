"""Unit tests for commerce service business logic."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

from src.commerce_service.repository import DB_PATH, Repository, init_db
from src.commerce_service.service import CommerceService


@pytest.fixture(scope="function")
def repo():
    """Create test repository with fresh database."""
    # Remove existing database
    if DB_PATH.exists():
        DB_PATH.unlink()

    # Initialize fresh database
    init_db()

    yield Repository()

    # Cleanup
    if DB_PATH.exists():
        DB_PATH.unlink()


@pytest.fixture
def service(repo):
    """Create service with test repository."""
    return CommerceService(repo)


class TestSKUOperations:
    """Tests for SKU creation and management."""

    def test_create_sku(self, service, repo):
        """Create a new SKU."""
        service.create_sku("SKU001", 100)
        sku = repo.get_sku("SKU001")
        assert sku is not None
        assert sku["stock"] == 100

    def test_adjust_stock_increase(self, service, repo):
        """Increase stock."""
        service.create_sku("SKU001", 50)
        result = service.adjust_stock("SKU001", 30)
        assert result["new_stock"] == 80

    def test_adjust_stock_decrease(self, service, repo):
        """Decrease stock."""
        service.create_sku("SKU001", 50)
        result = service.adjust_stock("SKU001", -20)
        assert result["new_stock"] == 30


class TestReservationCreation:
    """Tests for reservation creation logic."""

    def test_create_reservation_success(self, service, repo):
        """Successfully create a reservation."""
        service.create_sku("SKU001", 100)
        response, status = service.create_reservation("SKU001", 10, "key-123")
        assert status == 201
        assert response.status == "PENDING"
        assert response.sku == "SKU001"
        assert response.quantity == 10

    def test_create_reservation_deducts_stock(self, service, repo):
        """Creating reservation should deduct stock."""
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "key-123")
        sku = repo.get_sku("SKU001")
        assert sku["stock"] == 70

    def test_create_reservation_insufficient_stock(self, service, repo):
        """Cannot reserve more than available."""
        service.create_sku("SKU001", 10)
        response, status = service.create_reservation("SKU001", 20, "key-123")
        assert status == 400
        assert response["detail"] == "Insufficient stock"

    def test_create_reservation_idempotency_no_double_deduction(self, service, repo):
        """Same idempotency key should not deduct stock twice."""
        service.create_sku("SKU001", 100)

        # First request
        res1, status1 = service.create_reservation("SKU001", 20, "key-123")
        assert status1 == 201
        sku_after_first = repo.get_sku("SKU001")
        assert sku_after_first["stock"] == 80

        # Second request with same key
        res2, status2 = service.create_reservation("SKU001", 20, "key-123")
        assert status2 == 201
        assert res2.id == res1.id
        sku_after_second = repo.get_sku("SKU001")
        assert sku_after_second["stock"] == 80  # No double deduction

    def test_create_reservation_idempotency_returns_same_data(self, service, repo):
        """Idempotent request should return exact same reservation."""
        service.create_sku("SKU001", 100)

        res1, _ = service.create_reservation("SKU001", 15, "key-123")
        res2, _ = service.create_reservation("SKU001", 15, "key-123")

        assert res1.id == res2.id
        assert res1.sku == res2.sku
        assert res1.quantity == res2.quantity
        assert res1.status == res2.status


class TestReservationConfirmation:
    """Tests for reservation confirmation logic."""

    def test_confirm_pending_reservation(self, service, repo):
        """Confirm a PENDING reservation."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        response, status = service.confirm_reservation(res_id)
        assert status == 200
        assert response["status"] == "CONFIRMED"

    def test_confirm_creates_order(self, service, repo):
        """Confirming reservation should create an order."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        response, status = service.confirm_reservation(res_id)
        assert "order_id" in response
        order = repo._get_conn().execute(
            "SELECT * FROM orders WHERE id = ?", (response["order_id"],)
        ).fetchone()
        assert order is not None

    def test_confirm_non_pending_fails(self, service, repo):
        """Cannot confirm non-PENDING reservation."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        # Confirm once
        service.confirm_reservation(res_id)

        # Try again
        response, status = service.confirm_reservation(res_id)
        assert status == 400
        assert "not in PENDING state" in response["detail"]

    def test_confirm_expired_reservation(self, service, repo):
        """Cannot confirm reservation older than 300 seconds."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        # Manually set created_at to past
        conn = repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            ((datetime.utcnow() - timedelta(seconds=400)).isoformat(), res_id)
        )
        conn.commit()
        conn.close()

        response, status = service.confirm_reservation(res_id)
        assert status == 400
        assert response["detail"] == "Reservation expired"

    def test_confirm_expired_marks_as_expired(self, service, repo):
        """Confirming expired reservation should mark it as EXPIRED."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        # Manually set created_at to past
        conn = repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            ((datetime.utcnow() - timedelta(seconds=400)).isoformat(), res_id)
        )
        conn.commit()
        conn.close()

        service.confirm_reservation(res_id)

        res = repo.get_reservation(res_id)
        assert res["status"] == "EXPIRED"

    def test_confirm_expired_restores_stock(self, service, repo):
        """Confirming expired reservation should restore stock."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 20, "key-123")
        res_id = res_resp.id

        # Manually set created_at to past
        conn = repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            ((datetime.utcnow() - timedelta(seconds=400)).isoformat(), res_id)
        )
        conn.commit()
        conn.close()

        service.confirm_reservation(res_id)

        sku = repo.get_sku("SKU001")
        assert sku["stock"] == 100  # Stock restored


class TestReservationCancellation:
    """Tests for reservation cancellation logic."""

    def test_cancel_pending_reservation(self, service, repo):
        """Cancel a PENDING reservation."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        response, status = service.cancel_reservation(res_id)
        assert status == 200
        assert response["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, service, repo):
        """Cancelling reservation should restore stock."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 25, "key-123")
        res_id = res_resp.id

        service.cancel_reservation(res_id)

        sku = repo.get_sku("SKU001")
        assert sku["stock"] == 100

    def test_cancel_non_pending_fails(self, service, repo):
        """Cannot cancel non-PENDING reservation."""
        service.create_sku("SKU001", 100)
        res_resp, _ = service.create_reservation("SKU001", 10, "key-123")
        res_id = res_resp.id

        # Confirm first
        service.confirm_reservation(res_id)

        # Try to cancel
        response, status = service.cancel_reservation(res_id)
        assert status == 400
        assert "not in PENDING state" in response["detail"]


class TestOrders:
    """Tests for order listing and pagination."""

    def test_get_orders_pagination(self, service, repo):
        """Get paginated orders."""
        # Create and confirm orders
        service.create_sku("SKU001", 1000)
        for i in range(5):
            res_resp, _ = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(res_resp.id)

        # Get first page
        result = service.get_orders(page=1, size=10)
        assert len(result.items) == 5
        assert result.total == 5

    def test_get_orders_pagination_multiple_pages(self, service, repo):
        """Pagination should work with multiple pages."""
        service.create_sku("SKU001", 1000)
        for i in range(15):
            res_resp, _ = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(res_resp.id)

        # Page 1
        page1 = service.get_orders(page=1, size=10)
        assert len(page1.items) == 10
        assert page1.total == 15

        # Page 2
        page2 = service.get_orders(page=2, size=10)
        assert len(page2.items) == 5
        assert page2.total == 15

    def test_get_orders_with_custom_page_size(self, service, repo):
        """Custom page size should work."""
        service.create_sku("SKU001", 1000)
        for i in range(25):
            res_resp, _ = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(res_resp.id)

        result = service.get_orders(page=1, size=5)
        assert len(result.items) == 5
        assert result.total == 25
