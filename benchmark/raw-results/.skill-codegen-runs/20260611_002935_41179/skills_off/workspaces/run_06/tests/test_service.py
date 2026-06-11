"""Tests for the service layer."""

import pytest
from datetime import datetime
from commerce_service.repository import Repository
from commerce_service.service import CommerceService, RESERVATION_EXPIRATION_SECONDS


@pytest.fixture
def repository():
    """Create an in-memory repository for testing."""
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repository):
    """Create a service instance."""
    return CommerceService(repository)


class TestSKUManagement:
    def test_create_sku(self, service):
        """Test creating a new SKU."""
        result = service.create_sku("SKU-001", 100)
        assert result["sku"] == "SKU-001"
        assert result["available_stock"] == 100
        assert result["id"] == 1

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", 50)
        assert result["new_stock"] == 150

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", -30)
        assert result["new_stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(ValueError, match="SKU not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        """Test successful reservation creation."""
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 50, "idempotency-1")
        assert result.id == 1
        assert result.sku == "SKU-001"
        assert result.quantity == 50
        assert result.status == "PENDING"
        assert result.idempotency_key == "idempotency-1"

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails when stock is insufficient."""
        service.create_sku("SKU-001", 50)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU-001", 100, "idempotency-1")

    def test_create_reservation_exact_stock(self, service):
        """Test reservation succeeds with exact stock amount."""
        service.create_sku("SKU-001", 50)
        result = service.create_reservation("SKU-001", 50, "idempotency-1")
        assert result.quantity == 50
        assert result.status == "PENDING"

    def test_create_reservation_idempotency(self, service):
        """Test idempotent reservation requests."""
        service.create_sku("SKU-001", 100)

        first = service.create_reservation("SKU-001", 50, "idempotency-1")
        second = service.create_reservation("SKU-001", 50, "idempotency-1")

        assert first.id == second.id
        assert first.quantity == second.quantity
        assert first.status == second.status

        sku_info = service.repo.get_sku_by_name("SKU-001")
        assert sku_info["available_stock"] == 50

    def test_create_reservation_nonexistent_sku(self, service):
        """Test reservation fails for non-existent SKU."""
        with pytest.raises(ValueError, match="SKU not found"):
            service.create_reservation("NONEXISTENT", 10, "idempotency-1")


class TestConfirmation:
    def test_confirm_reservation_happy_path(self, service):
        """Test confirming a pending reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

        result = service.confirm_reservation(reservation.id)
        assert result.id == reservation.id
        assert result.status == "CONFIRMED"
        assert result.order_id == 1

        order = service.repo.get_order(result.order_id)
        assert order is not None
        assert order["reservation_id"] == reservation.id

    def test_confirm_reservation_nonexistent(self, service):
        """Test confirming non-existent reservation."""
        with pytest.raises(ValueError, match="not found"):
            service.confirm_reservation(999)

    def test_confirm_reservation_not_pending(self, service):
        """Test confirming a non-PENDING reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

        service.confirm_reservation(reservation.id)

        with pytest.raises(ValueError, match="not PENDING"):
            service.confirm_reservation(reservation.id)

    def test_confirm_reservation_expired(self, service, monkeypatch):
        """Test confirming an expired reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

        def mock_utcnow():
            original = datetime.fromisoformat(reservation.created_at)
            return original.replace(microsecond=0) + __import__('datetime').timedelta(
                seconds=RESERVATION_EXPIRATION_SECONDS + 1
            )

        monkeypatch.setattr(__import__('commerce_service.service', fromlist=['datetime']).datetime, 'utcnow', mock_utcnow)

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(reservation.id)

        updated_reservation = service.repo.get_reservation(reservation.id)
        assert updated_reservation["status"] == "EXPIRED"

        sku_info = service.repo.get_sku_by_name("SKU-001")
        assert sku_info["available_stock"] == 100


class TestCancellation:
    def test_cancel_reservation_happy_path(self, service):
        """Test cancelling a pending reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

        sku_before = service.repo.get_sku_by_name("SKU-001")
        assert sku_before["available_stock"] == 50

        result = service.cancel_reservation(reservation.id)
        assert result["status"] == "CANCELLED"

        sku_after = service.repo.get_sku_by_name("SKU-001")
        assert sku_after["available_stock"] == 100

    def test_cancel_reservation_nonexistent(self, service):
        """Test cancelling non-existent reservation."""
        with pytest.raises(ValueError, match="not found"):
            service.cancel_reservation(999)

    def test_cancel_reservation_not_pending(self, service):
        """Test cancelling a non-PENDING reservation."""
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 50, "idempotency-1")

        service.confirm_reservation(reservation.id)

        with pytest.raises(ValueError, match="not PENDING"):
            service.cancel_reservation(reservation.id)


class TestOrders:
    def test_list_orders_empty(self, service):
        """Test listing orders when none exist."""
        result = service.list_orders(page=1, size=10)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["size"] == 10

    def test_list_orders_pagination(self, service):
        """Test order pagination."""
        service.create_sku("SKU-001", 1000)

        for i in range(25):
            reservation = service.create_reservation("SKU-001", 1, f"idempotency-{i}")
            service.confirm_reservation(reservation.id)

        page1 = service.list_orders(page=1, size=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 25

        page2 = service.list_orders(page=2, size=10)
        assert len(page2["items"]) == 10

        page3 = service.list_orders(page=3, size=10)
        assert len(page3["items"]) == 5

        page4 = service.list_orders(page=4, size=10)
        assert len(page4["items"]) == 0
