import pytest
from datetime import datetime, timedelta

from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    DuplicateReservationError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return Service(repo)


def test_create_sku(service):
    sku = service.create_sku("PROD-001", "Test Product")
    assert sku.id is not None
    assert sku.code == "PROD-001"
    assert sku.name == "Test Product"


def test_adjust_stock(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)
    stock = service.repo.get_stock(sku.id)
    assert stock.available_qty == 100


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock(999, 100)


def test_create_reservation_happy_path(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
        reservation_ttl_seconds=300,
    )

    assert reservation.id is not None
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 10
    assert reservation.idempotency_key == "key-123"

    # Verify stock was reserved
    stock = service.repo.get_stock(sku.id)
    assert stock.available_qty == 90
    assert stock.reserved_qty == 10


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(
            sku_id=sku.id,
            quantity=10,
            idempotency_key="key-123",
        )


def test_create_reservation_idempotent(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation1 = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
    )

    # Retry with same key returns same reservation
    reservation2 = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
    )

    assert reservation1.id == reservation2.id

    # Stock should only be reserved once
    stock = service.repo.get_stock(sku.id)
    assert stock.reserved_qty == 10


def test_create_reservation_duplicate_cancelled_key(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
    )

    service.cancel_reservation(reservation.id)

    with pytest.raises(DuplicateReservationError):
        service.create_reservation(
            sku_id=sku.id,
            quantity=10,
            idempotency_key="key-123",
        )


def test_confirm_reservation(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
    )

    order = service.confirm_reservation(reservation.id)

    assert order.id is not None
    assert order.reservation_id == reservation.id
    assert order.sku_id == sku.id
    assert order.quantity == 10

    # Verify reservation is confirmed
    updated_reservation = service.repo.get_reservation(reservation.id)
    assert updated_reservation.status.value == "confirmed"


def test_confirm_reservation_expired(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
        reservation_ttl_seconds=1,
    )

    # Move time forward
    import time
    time.sleep(1.1)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(
        sku_id=sku.id,
        quantity=10,
        idempotency_key="key-123",
    )

    service.cancel_reservation(reservation.id)

    # Verify stock was released
    stock = service.repo.get_stock(sku.id)
    assert stock.available_qty == 100
    assert stock.reserved_qty == 0

    # Verify reservation is cancelled
    updated_reservation = service.repo.get_reservation(reservation.id)
    assert updated_reservation.status.value == "cancelled"


def test_get_orders_pagination(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 100)

    # Create multiple orders
    for i in range(15):
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=1,
            idempotency_key=f"key-{i}",
        )
        service.confirm_reservation(reservation.id)

    # Test pagination
    orders, total = service.get_orders(offset=0, limit=10)
    assert len(orders) == 10
    assert total == 15

    orders, total = service.get_orders(offset=10, limit=10)
    assert len(orders) == 5
    assert total == 15
