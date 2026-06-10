import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def mock_repo():
    return MagicMock(spec=Repository)


@pytest.fixture
def service(mock_repo):
    return CommerceService(mock_repo)


def test_create_sku_success(service, mock_repo):
    mock_repo.create_sku.return_value = True
    result = service.create_sku("SKU123", 100)
    assert result["sku"] == "SKU123"
    assert result["initial_stock"] == 100
    mock_repo.create_sku.assert_called_once_with("SKU123", 100)


def test_create_sku_duplicate(service, mock_repo):
    mock_repo.create_sku.return_value = False
    with pytest.raises(ValueError, match="SKU already exists"):
        service.create_sku("SKU123", 100)


def test_adjust_stock_success(service, mock_repo):
    mock_repo.adjust_stock.return_value = 150
    result = service.adjust_stock("SKU123", 50)
    assert result["sku"] == "SKU123"
    assert result["available_stock"] == 150
    mock_repo.adjust_stock.assert_called_once_with("SKU123", 50)


def test_adjust_stock_sku_not_found(service, mock_repo):
    mock_repo.adjust_stock.return_value = None
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("NONEXISTENT", 50)


def test_create_reservation_success(service, mock_repo):
    mock_repo.get_reservation_by_idempotency_key.return_value = None
    mock_repo.get_sku_stock.return_value = 100
    mock_repo.adjust_stock.return_value = 50
    mock_repo.create_reservation.return_value = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "PENDING",
        "created_at": datetime.utcnow().isoformat(),
        "idempotency_key": "key123",
    }

    result = service.create_reservation("SKU123", 50, "key123")
    assert result["id"] == 1
    assert result["status"] == "PENDING"
    mock_repo.get_sku_stock.assert_called_once_with("SKU123")
    mock_repo.adjust_stock.assert_called_once_with("SKU123", -50)


def test_create_reservation_idempotent(service, mock_repo):
    existing_reservation = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "PENDING",
        "created_at": datetime.utcnow().isoformat(),
        "idempotency_key": "key123",
    }
    mock_repo.get_reservation_by_idempotency_key.return_value = existing_reservation

    result = service.create_reservation("SKU123", 50, "key123")
    assert result == existing_reservation
    mock_repo.get_sku_stock.assert_not_called()
    mock_repo.adjust_stock.assert_not_called()


def test_create_reservation_insufficient_stock(service, mock_repo):
    mock_repo.get_reservation_by_idempotency_key.return_value = None
    mock_repo.get_sku_stock.return_value = 30
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU123", 50, "key123")


def test_create_reservation_sku_not_found(service, mock_repo):
    mock_repo.get_reservation_by_idempotency_key.return_value = None
    mock_repo.get_sku_stock.return_value = None
    with pytest.raises(ValueError, match="SKU not found"):
        service.create_reservation("NONEXISTENT", 50, "key123")


def test_confirm_reservation_success(service, mock_repo):
    created_at = datetime.utcnow().isoformat()
    mock_repo.get_reservation.return_value = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "PENDING",
        "created_at": created_at,
        "idempotency_key": "key123",
    }
    mock_repo.create_order.return_value = 101

    result = service.confirm_reservation(1)
    assert result["status"] == "CONFIRMED"
    mock_repo.update_reservation_status.assert_called_once_with(1, "CONFIRMED")
    mock_repo.create_order.assert_called_once_with(1, "SKU123", 50)


def test_confirm_reservation_not_found(service, mock_repo):
    mock_repo.get_reservation.return_value = None
    with pytest.raises(ValueError, match="Reservation not found"):
        service.confirm_reservation(1)


def test_confirm_reservation_not_pending(service, mock_repo):
    mock_repo.get_reservation.return_value = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "CONFIRMED",
        "created_at": datetime.utcnow().isoformat(),
        "idempotency_key": "key123",
    }
    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(1)


def test_confirm_reservation_expired(service, mock_repo):
    old_time = datetime.utcnow() - timedelta(seconds=400)
    mock_repo.get_reservation.return_value = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "PENDING",
        "created_at": old_time.isoformat(),
        "idempotency_key": "key123",
    }

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(1)

    mock_repo.update_reservation_status.assert_called_once_with(1, "EXPIRED")
    mock_repo.adjust_stock.assert_called_once_with("SKU123", 50)


def test_cancel_reservation_success(service, mock_repo):
    mock_repo.get_reservation.return_value = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "PENDING",
        "created_at": datetime.utcnow().isoformat(),
        "idempotency_key": "key123",
    }

    result = service.cancel_reservation(1)
    assert result["status"] == "CANCELLED"
    mock_repo.update_reservation_status.assert_called_once_with(1, "CANCELLED")
    mock_repo.adjust_stock.assert_called_once_with("SKU123", 50)


def test_cancel_reservation_not_pending(service, mock_repo):
    mock_repo.get_reservation.return_value = {
        "id": 1,
        "sku": "SKU123",
        "quantity": 50,
        "status": "CANCELLED",
        "created_at": datetime.utcnow().isoformat(),
        "idempotency_key": "key123",
    }
    with pytest.raises(ValueError, match="not in PENDING state"):
        service.cancel_reservation(1)
