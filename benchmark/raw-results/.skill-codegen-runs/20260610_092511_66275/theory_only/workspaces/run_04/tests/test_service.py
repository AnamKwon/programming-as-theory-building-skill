import pytest

from src.commerce_service.models import ReservationState
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationAlreadyCancelledError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SkuNotFoundError,
)


@pytest.fixture
def service():
    repo = Repository()
    return CommerceService(repo)


def test_create_sku(service):
    sku = service.create_sku("WIDGET-001", "Blue Widget", 100)
    assert sku.sku_id == "WIDGET-001"
    assert sku.name == "Blue Widget"
    assert sku.total_stock == 100
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_adjust_stock_positive(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    sku = service.adjust_stock("WIDGET-001", 50)
    assert sku.total_stock == 150
    assert sku.available_stock == 150


def test_adjust_stock_negative(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    sku = service.adjust_stock("WIDGET-001", -30)
    assert sku.total_stock == 70
    assert sku.available_stock == 70


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(SkuNotFoundError):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_happy_path(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "idempotency-key-1")
    assert res.reservation_id is not None
    assert res.customer_id == "customer-123"
    assert res.sku_id == "WIDGET-001"
    assert res.quantity == 10
    assert res.state == ReservationState.PENDING


def test_create_reservation_insufficient_stock(service):
    service.create_sku("WIDGET-001", "Blue Widget", 5)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")


def test_create_reservation_sku_not_found(service):
    with pytest.raises(SkuNotFoundError):
        service.create_reservation("customer-123", "NONEXISTENT", 10, "key-1")


def test_create_reservation_idempotency(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res1 = service.create_reservation("customer-123", "WIDGET-001", 10, "idempotency-key-1")
    res2 = service.create_reservation("customer-123", "WIDGET-001", 10, "idempotency-key-1")
    assert res1.reservation_id == res2.reservation_id


def test_reservation_state_affects_available_stock(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    service.create_reservation("customer-123", "WIDGET-001", 30, "key-1")
    sku = service.repo.get_sku("WIDGET-001")
    assert sku.available_stock == 70
    assert sku.reserved_stock == 30


def test_confirm_reservation_happy_path(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    confirmed = service.confirm_reservation(res.reservation_id)
    assert confirmed.state == ReservationState.CONFIRMED


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("nonexistent-id")


def test_confirm_reservation_already_confirmed(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    service.confirm_reservation(res.reservation_id)
    with pytest.raises(ReservationAlreadyConfirmedError):
        service.confirm_reservation(res.reservation_id)


def test_cancel_reservation_happy_path(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    cancelled = service.cancel_reservation(res.reservation_id)
    assert cancelled.state == ReservationState.CANCELLED


def test_cancel_reservation_already_cancelled(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    service.cancel_reservation(res.reservation_id)
    with pytest.raises(ReservationAlreadyCancelledError):
        service.cancel_reservation(res.reservation_id)


def test_cancel_confirmed_reservation_fails(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    service.confirm_reservation(res.reservation_id)
    with pytest.raises(ReservationAlreadyConfirmedError):
        service.cancel_reservation(res.reservation_id)


def test_create_order_from_confirmed_reservation(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    service.confirm_reservation(res.reservation_id)
    order = service.create_order_from_reservation(res.reservation_id)
    assert order.order_id is not None
    assert order.reservation_id == res.reservation_id
    assert order.customer_id == "customer-123"
    assert order.quantity == 10


def test_create_order_from_pending_reservation_fails(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    res = service.create_reservation("customer-123", "WIDGET-001", 10, "key-1")
    with pytest.raises(ValueError):
        service.create_order_from_reservation(res.reservation_id)


def test_list_orders_pagination(service):
    service.create_sku("WIDGET-001", "Blue Widget", 100)
    for i in range(15):
        res = service.create_reservation("customer-123", f"WIDGET-001", 1, f"key-{i}")
        service.confirm_reservation(res.reservation_id)
        service.create_order_from_reservation(res.reservation_id)

    orders, total = service.list_orders(limit=10, offset=0)
    assert len(orders) == 10
    assert total == 15

    orders, total = service.list_orders(limit=10, offset=10)
    assert len(orders) == 5
    assert total == 15
