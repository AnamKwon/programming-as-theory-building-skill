import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import ReservationStatus


@pytest.fixture
def repository():
    return Repository()


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", "Widget A", 100)
    assert sku.sku_id == "SKU-001"
    assert sku.name == "Widget A"
    assert sku.current_stock == 100
    assert sku.reserved_stock == 0


def test_create_duplicate_sku_raises_conflict(service):
    service.create_sku("SKU-001", "Widget A", 100)
    with pytest.raises(HTTPException) as exc:
        service.create_sku("SKU-001", "Widget B", 50)
    assert exc.value.status_code == 409


def test_adjust_stock(service):
    service.create_sku("SKU-001", "Widget A", 100)
    sku = service.adjust_stock("SKU-001", 10)
    assert sku.current_stock == 110

    sku = service.adjust_stock("SKU-001", -20)
    assert sku.current_stock == 90


def test_adjust_stock_nonexistent_sku_raises_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.adjust_stock("SKU-999", 10)
    assert exc.value.status_code == 404


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-1")

    assert res.sku_id == "SKU-001"
    assert res.quantity == 10
    assert res.status == ReservationStatus.PENDING


def test_create_reservation_idempotent(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res1 = service.create_reservation("SKU-001", 10, "idempotency-1")
    res2 = service.create_reservation("SKU-001", 10, "idempotency-1")

    assert res1.reservation_id == res2.reservation_id


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", "Widget A", 100)
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU-001", 150, "idempotency-1")
    assert exc.value.status_code == 409


def test_create_reservation_respects_existing_reservations(service):
    service.create_sku("SKU-001", "Widget A", 100)
    service.create_reservation("SKU-001", 60, "idempotency-1")

    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU-001", 50, "idempotency-2")
    assert exc.value.status_code == 409


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU-999", 10, "idempotency-1")
    assert exc.value.status_code == 404


def test_confirm_reservation(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-1")

    confirmed = service.confirm_reservation(res.reservation_id)
    assert confirmed.status == ReservationStatus.CONFIRMED
    assert confirmed.order_id is not None


def test_confirm_nonexistent_reservation(service):
    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation("RES-999")
    assert exc.value.status_code == 404


def test_confirm_already_confirmed_reservation(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-1")
    service.confirm_reservation(res.reservation_id)

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(res.reservation_id)
    assert exc.value.status_code == 409


def test_cancel_reservation(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-1")

    cancelled = service.cancel_reservation(res.reservation_id)
    assert cancelled.status == ReservationStatus.CANCELLED

    sku = service.get_sku("SKU-001")
    assert sku.reserved_stock == 0


def test_cancel_nonexistent_reservation(service):
    with pytest.raises(HTTPException) as exc:
        service.cancel_reservation("RES-999")
    assert exc.value.status_code == 404


def test_cancel_already_cancelled_reservation(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-1")
    service.cancel_reservation(res.reservation_id)

    cancelled = service.cancel_reservation(res.reservation_id)
    assert cancelled.status == ReservationStatus.CANCELLED


def test_get_order(service):
    service.create_sku("SKU-001", "Widget A", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-1")
    confirmed = service.confirm_reservation(res.reservation_id)

    order = service.get_order(confirmed.order_id)
    assert order.order_id == confirmed.order_id
    assert len(order.reservations) == 1


def test_get_nonexistent_order(service):
    with pytest.raises(HTTPException) as exc:
        service.get_order("ORDER-999")
    assert exc.value.status_code == 404


def test_list_orders_pagination(service):
    service.create_sku("SKU-001", "Widget A", 100)

    for i in range(5):
        res = service.create_reservation("SKU-001", 10, f"key-{i}")
        service.confirm_reservation(res.reservation_id)

    orders1, total = service.list_orders(skip=0, limit=3)
    orders2, total = service.list_orders(skip=3, limit=3)

    assert len(orders1) == 3
    assert len(orders2) == 2
    assert total == 5


def test_reservation_stock_tracking(service):
    service.create_sku("SKU-001", "Widget A", 100)

    sku = service.get_sku("SKU-001")
    assert sku.available_stock == 100

    res1 = service.create_reservation("SKU-001", 30, "key-1")
    sku = service.get_sku("SKU-001")
    assert sku.reserved_stock == 30
    assert sku.available_stock == 70

    res2 = service.create_reservation("SKU-001", 20, "key-2")
    sku = service.get_sku("SKU-001")
    assert sku.reserved_stock == 50
    assert sku.available_stock == 50

    service.cancel_reservation(res1.reservation_id)
    sku = service.get_sku("SKU-001")
    assert sku.reserved_stock == 20
    assert sku.available_stock == 80
