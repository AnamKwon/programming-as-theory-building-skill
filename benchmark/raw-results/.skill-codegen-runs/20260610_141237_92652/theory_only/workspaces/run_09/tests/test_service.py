import pytest
import time
from datetime import datetime
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService
from fastapi import HTTPException


@pytest.fixture
def test_db():
    repo = Repository(":memory:")
    yield repo
    repo.clear_db()


@pytest.fixture
def service(test_db):
    return CommerceService(test_db)


def test_create_sku(service, test_db):
    result = service.create_sku("WIDGET-001", 100)
    assert result["sku"] == "WIDGET-001"
    assert result["stock"] == 100
    assert test_db.get_sku_stock("WIDGET-001") == 100


def test_adjust_stock(service, test_db):
    service.create_sku("WIDGET-001", 100)
    result = service.adjust_stock("WIDGET-001", 25)
    assert result["new_stock"] == 125
    assert test_db.get_sku_stock("WIDGET-001") == 125


def test_adjust_stock_negative(service, test_db):
    service.create_sku("WIDGET-001", 100)
    result = service.adjust_stock("WIDGET-001", -30)
    assert result["new_stock"] == 70


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service, test_db):
    service.create_sku("WIDGET-001", 100)
    result = service.create_reservation("WIDGET-001", 25, "key-1")
    assert result.sku == "WIDGET-001"
    assert result.quantity == 25
    assert result.status == "PENDING"
    assert test_db.get_sku_stock("WIDGET-001") == 75


def test_create_reservation_insufficient_stock(service):
    service.create_sku("WIDGET-001", 20)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("WIDGET-001", 25, "key-1")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("NONEXISTENT", 10, "key-1")
    assert exc_info.value.status_code == 404


def test_reservation_idempotency(service, test_db):
    service.create_sku("WIDGET-001", 100)
    result1 = service.create_reservation("WIDGET-001", 25, "key-1")
    stock_after_first = test_db.get_sku_stock("WIDGET-001")

    result2 = service.create_reservation("WIDGET-001", 25, "key-1")
    stock_after_second = test_db.get_sku_stock("WIDGET-001")

    assert result1.id == result2.id
    assert stock_after_first == stock_after_second
    assert stock_after_first == 75


def test_confirm_reservation_success(service, test_db):
    service.create_sku("WIDGET-001", 100)
    reservation = service.create_reservation("WIDGET-001", 25, "key-1")
    order = service.confirm_reservation(reservation.id)

    assert order.sku == "WIDGET-001"
    assert order.quantity == 25
    assert order.reservation_id == reservation.id

    updated_res = test_db.get_reservation(reservation.id)
    assert updated_res["status"] == "CONFIRMED"


def test_confirm_reservation_nonexistent(service):
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(9999)
    assert exc_info.value.status_code == 404


def test_confirm_reservation_not_pending(service, test_db):
    service.create_sku("WIDGET-001", 100)
    reservation = service.create_reservation("WIDGET-001", 25, "key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_confirm_reservation_expired(service, test_db):
    service.create_sku("WIDGET-001", 100)
    reservation = service.create_reservation("WIDGET-001", 25, "key-1")

    past_time = datetime.utcnow().timestamp() - (CommerceService.RESERVATION_TTL_SECONDS + 10)
    conn = test_db._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (datetime.fromtimestamp(past_time).isoformat(), reservation.id),
    )
    conn.commit()
    conn.close()

    stock_before = test_db.get_sku_stock("WIDGET-001")
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert "Reservation expired" in exc_info.value.detail

    stock_after = test_db.get_sku_stock("WIDGET-001")
    assert stock_after == stock_before + 25

    updated_res = test_db.get_reservation(reservation.id)
    assert updated_res["status"] == "EXPIRED"


def test_cancel_reservation_success(service, test_db):
    service.create_sku("WIDGET-001", 100)
    reservation = service.create_reservation("WIDGET-001", 25, "key-1")
    stock_before = test_db.get_sku_stock("WIDGET-001")

    result = service.cancel_reservation(reservation.id)

    assert result["status"] == "CANCELLED"
    stock_after = test_db.get_sku_stock("WIDGET-001")
    assert stock_after == stock_before + 25


def test_cancel_reservation_not_pending(service, test_db):
    service.create_sku("WIDGET-001", 100)
    reservation = service.create_reservation("WIDGET-001", 25, "key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation.id)
    assert exc_info.value.status_code == 400


def test_cancel_reservation_nonexistent(service):
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(9999)
    assert exc_info.value.status_code == 404


def test_get_orders_pagination(service):
    service.create_sku("WIDGET-001", 1000)

    for i in range(25):
        res = service.create_reservation("WIDGET-001", 10, f"key-{i}")
        service.confirm_reservation(res.id)

    result = service.get_orders(page=1, size=10)
    assert len(result["orders"]) == 10
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 25

    result_page2 = service.get_orders(page=2, size=10)
    assert len(result_page2["orders"]) == 10
    assert result_page2["page"] == 2

    result_page3 = service.get_orders(page=3, size=10)
    assert len(result_page3["orders"]) == 5
    assert result_page3["page"] == 3


def test_happy_path_workflow(service, test_db):
    service.create_sku("GADGET-100", 50)
    assert test_db.get_sku_stock("GADGET-100") == 50

    reservation = service.create_reservation("GADGET-100", 15, "order-abc123")
    assert reservation.status == "PENDING"
    assert test_db.get_sku_stock("GADGET-100") == 35

    order = service.confirm_reservation(reservation.id)
    assert order.sku == "GADGET-100"
    assert order.quantity == 15
    assert test_db.get_sku_stock("GADGET-100") == 35

    orders = service.get_orders(page=1, size=10)
    assert len(orders["orders"]) == 1
    assert orders["total"] == 1
    assert orders["orders"][0].id == order.id
