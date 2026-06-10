"""Unit tests for the service layer."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.commerce_service.service import CommerceService
from src.commerce_service.models import Reservation


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    return Mock()


@pytest.fixture
def service(mock_repository):
    """Create a service with mocked repository."""
    return CommerceService(mock_repository)


def test_create_sku(service, mock_repository):
    """Test creating a SKU."""
    mock_sku = Mock(id=1, sku="SKU001", stock=100)
    mock_repository.create_sku.return_value = mock_sku

    result = service.create_sku("SKU001", 100)

    assert result.sku == "SKU001"
    assert result.stock == 100
    mock_repository.create_sku.assert_called_once_with("SKU001", 100)


def test_adjust_stock_success(service, mock_repository):
    """Test adjusting stock successfully."""
    mock_sku = Mock(id=1, sku="SKU001", stock=110)
    mock_repository.get_sku_by_name.return_value = Mock(id=1)
    mock_repository.update_sku_stock.return_value = mock_sku

    result = service.adjust_stock("SKU001", 10)

    assert result["sku"] == "SKU001"
    assert result["stock"] == 110
    mock_repository.get_sku_by_name.assert_called_once_with("SKU001")


def test_adjust_stock_sku_not_found(service, mock_repository):
    """Test adjusting stock for non-existent SKU."""
    mock_repository.get_sku_by_name.return_value = None

    with pytest.raises(Exception):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_idempotent(service, mock_repository):
    """Test that creating reservation with same idempotency key returns existing."""
    mock_reservation = Mock(id=1, sku="SKU001", quantity=5)
    mock_repository.get_reservation_by_idempotency_key.return_value = mock_reservation

    result = service.create_reservation("SKU001", 5, "key123")

    assert result.id == 1
    mock_repository.create_reservation.assert_not_called()


def test_create_reservation_insufficient_stock(service, mock_repository):
    """Test reservation fails when stock is insufficient."""
    mock_repository.get_reservation_by_idempotency_key.return_value = None
    mock_repository.get_sku_by_name.return_value = Mock(id=1, stock=3)

    with pytest.raises(Exception) as exc_info:
        service.create_reservation("SKU001", 5, "key123")

    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_success(service, mock_repository):
    """Test successful reservation creation."""
    mock_reservation = Mock(id=1, sku="SKU001", quantity=5, status="PENDING")
    mock_repository.get_reservation_by_idempotency_key.return_value = None
    mock_repository.get_sku_by_name.return_value = Mock(id=1, stock=10)
    mock_repository.update_sku_stock.return_value = Mock(stock=5)
    mock_repository.create_reservation.return_value = mock_reservation

    result = service.create_reservation("SKU001", 5, "key123")

    assert result.id == 1
    assert result.sku == "SKU001"
    assert result.quantity == 5
    mock_repository.update_sku_stock.assert_called_once_with(1, -5)


def test_confirm_reservation_success(service, mock_repository):
    """Test confirming a reservation."""
    created_time = datetime.utcnow()
    mock_reservation = Mock(
        id=1, status="PENDING", created_at=created_time, sku="SKU001", quantity=5
    )
    mock_order = Mock(id=1, reservation_id=1)
    mock_repository.get_reservation_by_id.return_value = mock_reservation
    mock_repository.update_reservation_status.return_value = mock_reservation
    mock_repository.create_order.return_value = mock_order

    result = service.confirm_reservation(1)

    assert result.id == 1
    mock_repository.update_reservation_status.assert_called_with(1, "CONFIRMED")
    mock_repository.create_order.assert_called_once_with(1)


def test_confirm_reservation_expired(service, mock_repository):
    """Test confirming an expired reservation."""
    created_time = datetime.utcnow() - timedelta(seconds=400)
    mock_reservation = Mock(
        id=1, status="PENDING", created_at=created_time, sku="SKU001", quantity=5
    )
    mock_repository.get_reservation_by_id.return_value = mock_reservation
    mock_repository.get_sku_by_name.return_value = Mock(id=1)

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(1)

    assert "Reservation expired" in str(exc_info.value)
    mock_repository.update_reservation_status.assert_called_with(1, "EXPIRED")
    mock_repository.update_sku_stock.assert_called_with(1, 5)


def test_confirm_reservation_not_pending(service, mock_repository):
    """Test confirming a non-PENDING reservation."""
    mock_reservation = Mock(id=1, status="CONFIRMED")
    mock_repository.get_reservation_by_id.return_value = mock_reservation

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(1)

    assert "Cannot confirm reservation" in str(exc_info.value)


def test_cancel_reservation_success(service, mock_repository):
    """Test canceling a reservation."""
    mock_reservation = Mock(
        id=1, status="PENDING", sku="SKU001", quantity=5
    )
    mock_repository.get_reservation_by_id.return_value = mock_reservation
    mock_repository.get_sku_by_name.return_value = Mock(id=1)
    mock_repository.update_reservation_status.return_value = mock_reservation

    result = service.cancel_reservation(1)

    assert result.id == 1
    mock_repository.update_reservation_status.assert_called_with(1, "CANCELLED")
    mock_repository.update_sku_stock.assert_called_with(1, 5)


def test_list_orders(service, mock_repository):
    """Test listing orders with pagination."""
    mock_orders = [Mock(id=1), Mock(id=2)]
    mock_repository.list_orders.return_value = (mock_orders, 5)

    result = service.list_orders(page=1, size=10)

    assert len(result["items"]) == 2
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 5
    mock_repository.list_orders.assert_called_once_with(1, 10)
