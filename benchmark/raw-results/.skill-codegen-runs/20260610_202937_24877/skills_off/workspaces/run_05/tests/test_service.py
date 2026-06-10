import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from src.commerce_service.service import CommerceService
from src.commerce_service.repository import Repository


@pytest.fixture
def service():
    return CommerceService()


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert result["reserved_stock"] == 0


def test_adjust_stock_increase(service):
    service.create_sku("SKU002", 50)
    result = service.adjust_stock("SKU002", 25)
    assert result["available_stock"] == 75


def test_adjust_stock_decrease(service):
    service.create_sku("SKU003", 100)
    result = service.adjust_stock("SKU003", -30)
    assert result["available_stock"] == 70


def test_create_reservation_success(service):
    service.create_sku("SKU004", 100)
    result = service.create_reservation("SKU004", 10, "idempotency-key-1")
    assert result["sku"] == "SKU004"
    assert result["quantity"] == 10
    assert result["status"] == "PENDING"
    assert result["idempotency_key"] == "idempotency-key-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU005", 5)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU005", 10, "idempotency-key-2")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU006", 100)
    first = service.create_reservation("SKU006", 20, "idempotency-key-3")
    second = service.create_reservation("SKU006", 20, "idempotency-key-3")
    assert first["id"] == second["id"]
    assert first == second


def test_confirm_reservation_success(service):
    service.create_sku("SKU007", 100)
    reservation = service.create_reservation("SKU007", 15, "idempotency-key-4")
    order = service.confirm_reservation(reservation["id"])
    assert order["status"] == "CONFIRMED"
    assert order["sku"] == "SKU007"
    assert order["quantity"] == 15


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU008", 100)
    reservation = service.create_reservation("SKU008", 10, "idempotency-key-5")
    service.confirm_reservation(reservation["id"])
    with pytest.raises(ValueError, match="not PENDING"):
        service.confirm_reservation(reservation["id"])


def test_confirm_reservation_expired(service):
    service.create_sku("SKU009", 100)

    with patch('src.commerce_service.service.datetime') as mock_datetime:
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)

        reservation = service.create_reservation("SKU009", 20, "idempotency-key-6")

        mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 6, 0)

        with pytest.raises(ValueError, match="Reservation expired"):
            service.confirm_reservation(reservation["id"])

        updated_res = service.repo.get_reservation(reservation["id"])
        assert updated_res["status"] == "EXPIRED"


def test_cancel_reservation_success(service):
    service.create_sku("SKU010", 100)
    reservation = service.create_reservation("SKU010", 25, "idempotency-key-7")
    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "CANCELLED"


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU011", 100)
    reservation = service.create_reservation("SKU011", 10, "idempotency-key-8")
    service.confirm_reservation(reservation["id"])
    with pytest.raises(ValueError, match="not PENDING"):
        service.cancel_reservation(reservation["id"])


def test_stock_restoration_on_cancel(service):
    service.create_sku("SKU012", 100)
    reservation = service.create_reservation("SKU012", 30, "idempotency-key-9")

    sku_before = service.repo.get_sku("SKU012")
    assert sku_before["available_stock"] == 70
    assert sku_before["reserved_stock"] == 30

    service.cancel_reservation(reservation["id"])

    sku_after = service.repo.get_sku("SKU012")
    assert sku_after["available_stock"] == 100
    assert sku_after["reserved_stock"] == 0


def test_get_orders_empty(service):
    orders, total = service.get_orders()
    assert orders == []
    assert total == 0


def test_get_orders_with_pagination(service):
    service.create_sku("SKU013", 1000)

    for i in range(25):
        res = service.create_reservation("SKU013", 5, f"idempotency-key-order-{i}")
        service.confirm_reservation(res["id"])

    page1, total1 = service.get_orders(page=1, size=10)
    assert len(page1) == 10
    assert total1 == 25

    page2, total2 = service.get_orders(page=2, size=10)
    assert len(page2) == 10
    assert total2 == 25

    page3, total3 = service.get_orders(page=3, size=10)
    assert len(page3) == 5
    assert total3 == 25
