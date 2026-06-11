import pytest
from pathlib import Path
import tempfile
from datetime import datetime, timedelta
from fastapi import HTTPException
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import (
    SKUCreate, StockAdjustRequest, ReservationCreate
)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        repo = Repository(db_path)
        repo.init_db()
        yield repo


@pytest.fixture
def service(temp_db):
    return CommerceService(temp_db)


def test_create_sku(service):
    request = SKUCreate(sku="TEST-SKU-001", initial_stock=100)
    result = service.create_sku(request)

    assert result.sku == "TEST-SKU-001"
    assert result.available_stock == 100
    assert result.reserved_stock == 0


def test_adjust_stock_positive(service):
    request = SKUCreate(sku="TEST-SKU-002", initial_stock=50)
    service.create_sku(request)

    adjust_request = StockAdjustRequest(sku="TEST-SKU-002", amount=30)
    result = service.adjust_stock(adjust_request)

    assert result["available_stock"] == 80


def test_adjust_stock_negative(service):
    request = SKUCreate(sku="TEST-SKU-003", initial_stock=50)
    service.create_sku(request)

    adjust_request = StockAdjustRequest(sku="TEST-SKU-003", amount=-20)
    result = service.adjust_stock(adjust_request)

    assert result["available_stock"] == 30


def test_adjust_stock_nonexistent_sku(service):
    adjust_request = StockAdjustRequest(sku="NONEXISTENT", amount=10)

    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(adjust_request)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    sku_request = SKUCreate(sku="TEST-SKU-004", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-004",
        quantity=30,
        idempotency_key="key-1"
    )
    result = service.create_reservation(res_request)

    assert result.sku == "TEST-SKU-004"
    assert result.quantity == 30
    assert result.status == "PENDING"


def test_create_reservation_insufficient_stock(service):
    sku_request = SKUCreate(sku="TEST-SKU-005", initial_stock=20)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-005",
        quantity=50,
        idempotency_key="key-2"
    )

    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(res_request)
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in str(exc_info.value.detail)


def test_create_reservation_idempotency(service):
    sku_request = SKUCreate(sku="TEST-SKU-006", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-006",
        quantity=25,
        idempotency_key="key-3"
    )

    first = service.create_reservation(res_request)
    second = service.create_reservation(res_request)

    assert first.id == second.id
    assert first.sku == second.sku
    assert first.quantity == second.quantity


def test_confirm_reservation_success(service):
    sku_request = SKUCreate(sku="TEST-SKU-007", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-007",
        quantity=30,
        idempotency_key="key-4"
    )
    reservation = service.create_reservation(res_request)

    result = service.confirm_reservation(reservation.id)

    assert result["status"] == "CONFIRMED"
    assert "order_id" in result


def test_confirm_reservation_not_found(service):
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_confirm_reservation_not_pending(service):
    sku_request = SKUCreate(sku="TEST-SKU-008", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-008",
        quantity=30,
        idempotency_key="key-5"
    )
    reservation = service.create_reservation(res_request)

    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert "not in PENDING state" in str(exc_info.value.detail)


def test_confirm_reservation_expired(service):
    sku_request = SKUCreate(sku="TEST-SKU-009", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-009",
        quantity=30,
        idempotency_key="key-6"
    )
    reservation = service.create_reservation(res_request)

    import sqlite3
    conn = sqlite3.connect(str(service.repo.db_path))
    cursor = conn.cursor()
    old_time = datetime.utcnow() - timedelta(seconds=400)
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time.isoformat(), reservation.id)
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert "Reservation expired" in str(exc_info.value.detail)

    updated = service.repo.get_reservation(reservation.id)
    assert updated["status"] == "EXPIRED"

    sku_data = service.repo.get_sku("TEST-SKU-009")
    assert sku_data["available_stock"] == 100


def test_cancel_reservation(service):
    sku_request = SKUCreate(sku="TEST-SKU-010", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-010",
        quantity=30,
        idempotency_key="key-7"
    )
    reservation = service.create_reservation(res_request)

    result = service.cancel_reservation(reservation.id)

    assert result["status"] == "CANCELLED"

    sku_data = service.repo.get_sku("TEST-SKU-010")
    assert sku_data["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    sku_request = SKUCreate(sku="TEST-SKU-011", initial_stock=100)
    service.create_sku(sku_request)

    res_request = ReservationCreate(
        sku="TEST-SKU-011",
        quantity=30,
        idempotency_key="key-8"
    )
    reservation = service.create_reservation(res_request)

    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_get_orders_pagination(service):
    sku_request = SKUCreate(sku="TEST-SKU-012", initial_stock=500)
    service.create_sku(sku_request)

    for i in range(25):
        res_request = ReservationCreate(
            sku="TEST-SKU-012",
            quantity=10,
            idempotency_key=f"order-key-{i}"
        )
        reservation = service.create_reservation(res_request)
        service.confirm_reservation(reservation.id)

    page1 = service.get_orders(page=1, size=10)
    assert page1.total == 25
    assert page1.page == 1
    assert page1.size == 10
    assert len(page1.orders) == 10

    page2 = service.get_orders(page=2, size=10)
    assert page2.total == 25
    assert page2.page == 2
    assert len(page2.orders) == 10

    page3 = service.get_orders(page=3, size=10)
    assert page3.total == 25
    assert page3.page == 3
    assert len(page3.orders) == 5
