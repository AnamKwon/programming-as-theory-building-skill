import pytest
import tempfile
from datetime import datetime, timedelta

from commerce_service.models import OrderState, ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        yield f.name


@pytest.fixture
def repo(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    assert sku.sku == "SKU-001"
    assert sku.name == "Product 1"
    assert sku.price == 29.99


def test_adjust_stock(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    stock = service.adjust_stock(sku.id, 100)
    assert stock.available == 100
    assert stock.reserved == 0
    assert stock.total == 100


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock(999, 10)


def test_create_reservation_happy_path(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 50
    assert reservation.state == ReservationState.PENDING

    # Check stock is updated
    stock = service.repo.get_stock(sku.id)
    assert stock.available == 50
    assert stock.reserved == 50


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 30)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 50, "idempotency-key-1")


def test_create_reservation_idempotent(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 100)

    reservation1 = service.create_reservation(sku.id, 50, "idempotency-key-1")
    reservation2 = service.create_reservation(sku.id, 50, "idempotency-key-1")

    assert reservation1.id == reservation2.id
    # Stock should not be double-reserved
    stock = service.repo.get_stock(sku.id)
    assert stock.reserved == 50


def test_confirm_reservation(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")

    confirmed, order = service.confirm_reservation(reservation.id)
    assert confirmed.state == ReservationState.CONFIRMED
    assert order.state == OrderState.CONFIRMED
    assert order.sku_id == sku.id
    assert order.quantity == 50


def test_cancel_reservation(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.state == ReservationState.CANCELLED

    # Check stock is released
    stock = service.repo.get_stock(sku.id)
    assert stock.available == 100
    assert stock.reserved == 0


def test_cancel_reservation_already_cancelled_is_idempotent(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 100)
    reservation = service.create_reservation(sku.id, 50, "idempotency-key-1")

    service.cancel_reservation(reservation.id)
    cancelled2 = service.cancel_reservation(reservation.id)
    assert cancelled2.state == ReservationState.CANCELLED


def test_reservation_expiration(service, repo):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 100)

    # Create reservation manually with past expiry (1 hour ago)
    now = datetime.utcnow()
    past_expires = now - timedelta(hours=1)
    reservation = repo.create_reservation(sku.id, 50, past_expires, "idempotency-key-1")

    # Verify reservation is still pending before calling confirm
    assert reservation.state == ReservationState.PENDING

    # Try to confirm it - should fail because it's expired
    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    # After confirm_reservation call (which calls expire_reservations internally),
    # the reservation should be marked as EXPIRED and stock released
    expired_res = repo.get_reservation(reservation.id)
    assert expired_res.state == ReservationState.EXPIRED

    stock = service.repo.get_stock(sku.id)
    assert stock.reserved == 0
    assert stock.available == 100


def test_get_orders_pagination(service):
    sku = service.create_sku("SKU-001", "Product 1", 29.99)
    service.adjust_stock(sku.id, 1000)

    # Create multiple orders
    for i in range(15):
        reservation = service.create_reservation(sku.id, 10, f"key-{i}")
        service.confirm_reservation(reservation.id)

    # Test pagination
    orders1, total = service.get_orders(limit=10, offset=0)
    assert len(orders1) == 10
    assert total == 15

    orders2, total = service.get_orders(limit=10, offset=10)
    assert len(orders2) == 5
    assert total == 15

    # Check no duplicates
    ids1 = {o.id for o in orders1}
    ids2 = {o.id for o in orders2}
    assert len(ids1 & ids2) == 0
