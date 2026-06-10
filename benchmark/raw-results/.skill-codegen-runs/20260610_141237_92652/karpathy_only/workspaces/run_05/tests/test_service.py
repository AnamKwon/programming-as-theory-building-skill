import pytest
import time
import os
from unittest.mock import patch
from commerce_service import init_db
from commerce_service.service import CommerceService
from commerce_service.repository import Repository
from fastapi import HTTPException

@pytest.fixture(autouse=True)
def setup_db():
    with patch.dict(os.environ, {"DB_PATH": ":memory:"}):
        init_db()
        yield
        # Cleanup happens automatically with in-memory DB

@pytest.fixture
def service():
    return CommerceService()

def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["stock"] == 100

def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 10)
    assert result["sku"] == "SKU001"
    assert result["stock"] == 110

    result = service.adjust_stock("SKU001", -20)
    assert result["stock"] == 90

def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 50)
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU001", 100, "key1")
    assert exc.value.status_code == 400
    assert "Insufficient stock" in str(exc.value.detail)

def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "key1")
    assert res.id == 1
    assert res.sku == "SKU001"
    assert res.quantity == 30
    assert res.status == "PENDING"

    stock = Repository.get_sku_stock("SKU001")
    assert stock == 70

def test_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    res1 = service.create_reservation("SKU001", 30, "key1")
    res2 = service.create_reservation("SKU001", 30, "key1")

    assert res1.id == res2.id
    assert res1.created_at == res2.created_at

    stock = Repository.get_sku_stock("SKU001")
    assert stock == 70

def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "key1")
    order = service.confirm_reservation(res.id)

    assert order.reservation_id == res.id
    assert order.id is not None

    reservation = Repository.get_reservation(res.id)
    assert reservation["status"] == "CONFIRMED"

def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "key1")
    service.cancel_reservation(res.id)

    reservation = Repository.get_reservation(res.id)
    assert reservation["status"] == "CANCELLED"

    stock = Repository.get_sku_stock("SKU001")
    assert stock == 100

def test_reservation_expiration(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "key1")

    with patch('commerce_service.service.time.time') as mock_time:
        mock_time.return_value = res.created_at + 301

        with pytest.raises(HTTPException) as exc:
            service.confirm_reservation(res.id)
        assert exc.value.status_code == 400
        assert "Reservation expired" in str(exc.value.detail)

    stock = Repository.get_sku_stock("SKU001")
    assert stock == 100

    reservation = Repository.get_reservation(res.id)
    assert reservation["status"] == "EXPIRED"

def test_confirm_non_pending_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "key1")
    service.confirm_reservation(res.id)

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(res.id)
    assert exc.value.status_code == 400

def test_cancel_non_pending_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 30, "key1")
    service.confirm_reservation(res.id)

    with pytest.raises(HTTPException) as exc:
        service.cancel_reservation(res.id)
    assert exc.value.status_code == 400

def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU001", 10, f"key{i}")
        service.confirm_reservation(res.id)

    page1 = service.get_orders(page=1, size=10)
    assert len(page1.orders) == 10
    assert page1.total == 25
    assert page1.page == 1
    assert page1.size == 10

    page2 = service.get_orders(page=2, size=10)
    assert len(page2.orders) == 10
    assert page2.page == 2

    page3 = service.get_orders(page=3, size=10)
    assert len(page3.orders) == 5
    assert page3.page == 3
