"""Unit tests for service layer."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.commerce_service.service import CommerceService
from src.commerce_service.repository import ReservationModel, SKUModel, OrderModel


@pytest.fixture
def mock_repo():
    """Create a mock repository."""
    return MagicMock()


@pytest.fixture
def service(mock_repo):
    """Create a service instance with mock repository."""
    return CommerceService(mock_repo)


class TestCreateSKU:
    """Test SKU creation."""

    def test_create_sku_success(self, service, mock_repo):
        """Test successful SKU creation."""
        sku_model = SKUModel(sku="TEST-001", stock=100)
        mock_repo.create_sku.return_value = sku_model

        result = service.create_sku("TEST-001", 100)

        assert result.sku == "TEST-001"
        assert result.stock == 100
        mock_repo.create_sku.assert_called_once_with("TEST-001", 100)


class TestAdjustStock:
    """Test stock adjustments."""

    def test_adjust_stock_positive(self, service, mock_repo):
        """Test positive stock adjustment."""
        sku_model = SKUModel(sku="TEST-001", stock=100)
        mock_repo.get_sku.return_value = sku_model
        updated_model = SKUModel(sku="TEST-001", stock=150)
        mock_repo.update_sku_stock.return_value = updated_model

        result = service.adjust_stock("TEST-001", 50)

        assert result.stock == 150

    def test_adjust_stock_negative(self, service, mock_repo):
        """Test negative stock adjustment."""
        sku_model = SKUModel(sku="TEST-001", stock=100)
        mock_repo.get_sku.return_value = sku_model
        updated_model = SKUModel(sku="TEST-001", stock=50)
        mock_repo.update_sku_stock.return_value = updated_model

        result = service.adjust_stock("TEST-001", -50)

        assert result.stock == 50

    def test_adjust_stock_sku_not_found(self, service, mock_repo):
        """Test adjustment for non-existent SKU."""
        mock_repo.get_sku.return_value = None

        with pytest.raises(Exception):
            service.adjust_stock("NONEXISTENT", 10)

    def test_adjust_stock_below_zero(self, service, mock_repo):
        """Test adjustment resulting in negative stock."""
        sku_model = SKUModel(sku="TEST-001", stock=10)
        mock_repo.get_sku.return_value = sku_model

        with pytest.raises(Exception):
            service.adjust_stock("TEST-001", -20)


class TestCreateReservation:
    """Test reservation creation."""

    def test_create_reservation_success(self, service, mock_repo):
        """Test successful reservation creation."""
        sku_model = SKUModel(sku="TEST-001", stock=100)
        mock_repo.get_sku.return_value = sku_model
        mock_repo.get_reservation_by_idempotency_key.return_value = None

        reservation = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="PENDING",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        mock_repo.create_reservation.return_value = reservation

        result = service.create_reservation("TEST-001", 10, "key-1")

        assert result.id == 1
        assert result.status == "PENDING"
        assert result.quantity == 10

    def test_create_reservation_idempotent(self, service, mock_repo):
        """Test idempotent reservation creation."""
        existing = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="PENDING",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        mock_repo.get_reservation_by_idempotency_key.return_value = existing

        result = service.create_reservation("TEST-001", 10, "key-1")

        assert result.id == 1
        mock_repo.create_reservation.assert_not_called()

    def test_create_reservation_insufficient_stock(self, service, mock_repo):
        """Test reservation with insufficient stock."""
        sku_model = SKUModel(sku="TEST-001", stock=5)
        mock_repo.get_sku.return_value = sku_model
        mock_repo.get_reservation_by_idempotency_key.return_value = None

        with pytest.raises(Exception):
            service.create_reservation("TEST-001", 10, "key-1")

    def test_create_reservation_sku_not_found(self, service, mock_repo):
        """Test reservation for non-existent SKU."""
        mock_repo.get_sku.return_value = None
        mock_repo.get_reservation_by_idempotency_key.return_value = None

        with pytest.raises(Exception):
            service.create_reservation("NONEXISTENT", 10, "key-1")


class TestConfirmReservation:
    """Test reservation confirmation."""

    def test_confirm_reservation_success(self, service, mock_repo):
        """Test successful reservation confirmation."""
        reservation = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="PENDING",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        confirmed = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="CONFIRMED",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        mock_repo.get_reservation.side_effect = [reservation, confirmed]

        result = service.confirm_reservation(1)

        assert result.status == "CONFIRMED"
        mock_repo.create_order.assert_called_once_with(1)

    def test_confirm_reservation_not_found(self, service, mock_repo):
        """Test confirmation of non-existent reservation."""
        mock_repo.get_reservation.return_value = None

        with pytest.raises(Exception):
            service.confirm_reservation(999)

    def test_confirm_reservation_wrong_status(self, service, mock_repo):
        """Test confirmation of non-pending reservation."""
        reservation = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="CANCELLED",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        mock_repo.get_reservation.return_value = reservation

        with pytest.raises(Exception):
            service.confirm_reservation(1)

    def test_confirm_reservation_expired(self, service, mock_repo):
        """Test confirmation of expired reservation."""
        old_time = datetime.utcnow() - timedelta(seconds=400)
        reservation = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="PENDING",
            idempotency_key="key-1", created_at=old_time
        )
        sku_model = SKUModel(sku="TEST-001", stock=90)
        mock_repo.get_reservation.return_value = reservation
        mock_repo.get_sku.return_value = sku_model

        with pytest.raises(Exception):
            service.confirm_reservation(1)

        mock_repo.update_reservation_status.assert_called_once_with(1, "EXPIRED")


class TestCancelReservation:
    """Test reservation cancellation."""

    def test_cancel_reservation_success(self, service, mock_repo):
        """Test successful reservation cancellation."""
        reservation = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="PENDING",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        cancelled = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="CANCELLED",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        sku_model = SKUModel(sku="TEST-001", stock=90)
        mock_repo.get_reservation.side_effect = [reservation, cancelled]
        mock_repo.get_sku.return_value = sku_model

        result = service.cancel_reservation(1)

        assert result.status == "CANCELLED"

    def test_cancel_reservation_not_found(self, service, mock_repo):
        """Test cancellation of non-existent reservation."""
        mock_repo.get_reservation.return_value = None

        with pytest.raises(Exception):
            service.cancel_reservation(999)

    def test_cancel_reservation_wrong_status(self, service, mock_repo):
        """Test cancellation of non-pending reservation."""
        reservation = ReservationModel(
            id=1, sku="TEST-001", quantity=10, status="CONFIRMED",
            idempotency_key="key-1", created_at=datetime.utcnow()
        )
        mock_repo.get_reservation.return_value = reservation

        with pytest.raises(Exception):
            service.cancel_reservation(1)


class TestGetOrders:
    """Test order retrieval."""

    def test_get_orders_success(self, service, mock_repo):
        """Test successful orders retrieval."""
        order1 = OrderModel(id=1, reservation_id=1, created_at=datetime.utcnow())
        order2 = OrderModel(id=2, reservation_id=2, created_at=datetime.utcnow())
        mock_repo.get_orders.return_value = ([order1, order2], 2)

        orders, total = service.get_orders(page=1, size=10)

        assert len(orders) == 2
        assert total == 2

    def test_get_orders_pagination(self, service, mock_repo):
        """Test pagination parameters."""
        orders = [OrderModel(id=i, reservation_id=i, created_at=datetime.utcnow()) for i in range(1, 11)]
        mock_repo.get_orders.return_value = (orders, 25)

        result, total = service.get_orders(page=3, size=10)

        assert total == 25
        mock_repo.get_orders.assert_called_once_with(3, 10)
