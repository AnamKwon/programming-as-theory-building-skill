import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["initial_stock"] == 100


def test_adjust_stock_positive(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", 50)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 150


def test_adjust_stock_negative(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", -30)
    assert result["available_stock"] == 70


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation, status_code = service.create_reservation(
        "SKU-001", 30, "key-1"
    )
    assert status_code == 201
    assert reservation.id > 0
    assert reservation.sku == "SKU-001"
    assert reservation.quantity == 30
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "key-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("SKU-001", 150, "key-1")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in str(exc_info.value.detail)


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    reservation1, status1 = service.create_reservation(
        "SKU-001", 30, "key-1"
    )
    reservation2, status2 = service.create_reservation(
        "SKU-001", 30, "key-1"
    )
    assert status1 == 201
    assert status2 == 200
    assert reservation1.id == reservation2.id
    assert reservation1.quantity == reservation2.quantity

    available = service.repo.get_available_stock("SKU-001")
    assert available == 70


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 30, "key-1")
    result = service.confirm_reservation(reservation.id)
    assert result["status"] == "CONFIRMED"
    assert result["order_id"] > 0


def test_confirm_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 30, "key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_confirm_reservation_expired(service, repo):
    service.create_sku("SKU-001", 100)
    created_at = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    reservation_id = repo.create_reservation("SKU-001", 30, "key-1", created_at)
    repo.deduct_stock("SKU-001", 30)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation_id)
    assert exc_info.value.status_code == 400
    assert "expired" in str(exc_info.value.detail).lower()

    res = repo.get_reservation(reservation_id)
    assert res["status"] == "EXPIRED"

    available = repo.get_available_stock("SKU-001")
    assert available == 100


def test_cancel_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 30, "key-1")
    result = service.cancel_reservation(reservation.id)
    assert result["status"] == "CANCELLED"

    available = service.repo.get_available_stock("SKU-001")
    assert available == 100


def test_cancel_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 30, "key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_get_orders_empty(service):
    result = service.get_orders()
    assert result["orders"] == []
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 0


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 1000)
    for i in range(25):
        reservation, _ = service.create_reservation("SKU-001", 10, f"key-{i}")
        service.confirm_reservation(reservation.id)

    page1 = service.get_orders(page=1, size=10)
    assert len(page1["orders"]) == 10
    assert page1["total"] == 25

    page2 = service.get_orders(page=2, size=10)
    assert len(page2["orders"]) == 10

    page3 = service.get_orders(page=3, size=10)
    assert len(page3["orders"]) == 5
