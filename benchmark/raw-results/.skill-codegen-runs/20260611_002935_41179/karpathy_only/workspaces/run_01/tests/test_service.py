"""Unit tests for commerce service."""
import pytest
from datetime import datetime, timedelta
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create in-memory database for testing."""
    database = Database(db_path=":memory:")
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def service(db):
    """Create service instance."""
    return CommerceService(db)


class TestSKUOperations:
    """Test SKU operations."""

    def test_create_sku(self, service):
        """Test creating a new SKU."""
        result = service.create_sku("SKU001", 100)
        assert result["sku"] == "SKU001"
        assert result["available_stock"] == 100

    def test_adjust_stock_positive(self, service):
        """Test increasing stock."""
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["available_stock"] == 150

    def test_adjust_stock_negative(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["available_stock"] == 70


class TestReservations:
    """Test reservation operations."""

    def test_create_reservation_success(self, service):
        """Test successful reservation creation."""
        service.create_sku("SKU001", 100)
        response, status = service.create_reservation("SKU001", 50, "idempotency-1")

        assert status == "201"
        assert response["id"] == 1
        assert response["sku"] == "SKU001"
        assert response["quantity"] == 50
        assert response["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation with insufficient stock."""
        service.create_sku("SKU001", 30)
        response, status = service.create_reservation("SKU001", 50, "idempotency-1")

        assert status == "400"
        assert response is None

    def test_idempotent_reservation(self, service):
        """Test idempotent reservation creation."""
        service.create_sku("SKU001", 100)

        # First request
        response1, status1 = service.create_reservation("SKU001", 50, "idempotency-1")
        assert status1 == "201"
        assert response1["id"] == 1

        # Second request with same idempotency key
        response2, status2 = service.create_reservation("SKU001", 50, "idempotency-1")
        assert status2 == "200"
        assert response2["id"] == 1

        # Verify stock was only deducted once
        sku = service.sku_repo.get_sku("SKU001")
        assert sku["available_stock"] == 50

    def test_confirm_reservation_success(self, service):
        """Test successful reservation confirmation."""
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "idempotency-1")

        order, status = service.confirm_reservation(res["id"])

        assert status == "200"
        assert order["reservation_id"] == res["id"]

        # Verify reservation status
        reservation = service.reservation_repo.get_reservation(res["id"])
        assert reservation["status"] == "CONFIRMED"

    def test_confirm_reservation_expired(self, service):
        """Test confirming an expired reservation."""
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "idempotency-1")

        # Manually set created_at to 301 seconds ago
        conn = service.db.get_connection()
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservation SET created_at = ? WHERE id = ?",
            (old_time, res["id"]),
        )
        conn.commit()

        order, status = service.confirm_reservation(res["id"])

        assert status == "400_EXPIRED"
        assert order is None

        # Verify reservation is marked as EXPIRED
        reservation = service.reservation_repo.get_reservation(res["id"])
        assert reservation["status"] == "EXPIRED"

        # Verify stock was restored
        sku = service.sku_repo.get_sku("SKU001")
        assert sku["available_stock"] == 100

    def test_confirm_reservation_not_pending(self, service):
        """Test confirming a non-pending reservation."""
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "idempotency-1")

        # Confirm once
        service.confirm_reservation(res["id"])

        # Try to confirm again
        order, status = service.confirm_reservation(res["id"])

        assert status == "400"
        assert order is None

    def test_cancel_reservation_success(self, service):
        """Test successful reservation cancellation."""
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "idempotency-1")

        # Stock should be 50 after reservation
        sku = service.sku_repo.get_sku("SKU001")
        assert sku["available_stock"] == 50

        response, status = service.cancel_reservation(res["id"])

        assert status == "200"
        assert response["status"] == "CANCELLED"

        # Verify stock was restored
        sku = service.sku_repo.get_sku("SKU001")
        assert sku["available_stock"] == 100

    def test_cancel_reservation_not_pending(self, service):
        """Test canceling a non-pending reservation."""
        service.create_sku("SKU001", 100)
        res, _ = service.create_reservation("SKU001", 50, "idempotency-1")

        # Confirm the reservation
        service.confirm_reservation(res["id"])

        # Try to cancel
        response, status = service.cancel_reservation(res["id"])

        assert status == "400"
        assert response is None


class TestOrders:
    """Test order operations."""

    def test_get_orders_pagination(self, service):
        """Test order pagination."""
        service.create_sku("SKU001", 1000)

        # Create and confirm multiple reservations
        for i in range(15):
            res, _ = service.create_reservation("SKU001", 10, f"idempotency-{i}")
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
        """Test getting orders when none exist."""
        orders, total = service.get_orders(page=1, size=10)

        assert len(orders) == 0
        assert total == 0
