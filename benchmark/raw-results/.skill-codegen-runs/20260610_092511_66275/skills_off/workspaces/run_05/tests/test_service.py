import pytest
import tempfile
from datetime import datetime, timedelta

from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationAlreadyExistsError,
    InvalidReservationStateError
)
from commerce_service.models import ReservationStatus, OrderStatus


@pytest.fixture
def repo():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        db_path = f.name
    repo = Repository(db_path=db_path)
    yield repo


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    sku_id = service.create_sku("Widget", 100)
    assert sku_id > 0

    sku = service.get_sku(sku_id)
    assert sku is not None
    assert sku["name"] == "Widget"
    assert sku["quantity"] == 100


def test_adjust_stock_positive(service):
    sku_id = service.create_sku("Widget", 100)
    service.adjust_stock(sku_id, 50)
    sku = service.get_sku(sku_id)
    assert sku["quantity"] == 150


def test_adjust_stock_negative(service):
    sku_id = service.create_sku("Widget", 100)
    service.adjust_stock(sku_id, -30)
    sku = service.get_sku(sku_id)
    assert sku["quantity"] == 70


def test_adjust_stock_insufficient(service):
    sku_id = service.create_sku("Widget", 100)
    with pytest.raises(InsufficientStockError):
        service.adjust_stock(sku_id, -150)


def test_create_reservation_success(service):
    sku_id = service.create_sku("Widget", 100)
    reservation_id = service.create_reservation(
        sku_id=sku_id,
        quantity=30,
        expires_in_seconds=3600,
        idempotency_key="key-1"
    )
    assert reservation_id > 0

    reservation = service.get_reservation(reservation_id)
    assert reservation is not None
    assert reservation["sku_id"] == sku_id
    assert reservation["quantity"] == 30
    assert reservation["status"] == ReservationStatus.PENDING

    # Stock should be deducted
    sku = service.get_sku(sku_id)
    assert sku["quantity"] == 70


def test_create_reservation_insufficient_stock(service):
    sku_id = service.create_sku("Widget", 50)
    with pytest.raises(InsufficientStockError):
        service.create_reservation(
            sku_id=sku_id,
            quantity=100,
            expires_in_seconds=3600,
            idempotency_key="key-1"
        )


def test_create_reservation_duplicate_idempotency_key(service):
    sku_id = service.create_sku("Widget", 100)
    service.create_reservation(
        sku_id=sku_id,
        quantity=30,
        expires_in_seconds=3600,
        idempotency_key="key-1"
    )

    # Second request with same key should fail
    with pytest.raises(ReservationAlreadyExistsError):
        service.create_reservation(
            sku_id=sku_id,
            quantity=20,
            expires_in_seconds=3600,
            idempotency_key="key-1"
        )


def test_confirm_reservation_success(service):
    sku_id = service.create_sku("Widget", 100)
    reservation_id = service.create_reservation(
        sku_id=sku_id,
        quantity=30,
        expires_in_seconds=3600,
        idempotency_key="key-1"
    )

    service.confirm_reservation(reservation_id)

    reservation = service.get_reservation(reservation_id)
    assert reservation["status"] == ReservationStatus.CONFIRMED

    # Order should be created
    orders, total = service.list_orders()
    assert total == 1
    assert orders[0]["status"] == OrderStatus.COMPLETED


def test_confirm_reservation_expired(service):
    sku_id = service.create_sku("Widget", 100)

    # Create reservation with very short expiration
    reservation_id = service.create_reservation(
        sku_id=sku_id,
        quantity=30,
        expires_in_seconds=1,
        idempotency_key="key-1"
    )

    # Wait for expiration
    import time
    time.sleep(2)

    # Trying to confirm should fail
    with pytest.raises(InvalidReservationStateError):
        service.confirm_reservation(reservation_id)


def test_cancel_reservation_success(service):
    sku_id = service.create_sku("Widget", 100)
    reservation_id = service.create_reservation(
        sku_id=sku_id,
        quantity=30,
        expires_in_seconds=3600,
        idempotency_key="key-1"
    )

    # Stock should be deducted
    assert service.get_sku(sku_id)["quantity"] == 70

    service.cancel_reservation(reservation_id)

    reservation = service.get_reservation(reservation_id)
    assert reservation["status"] == ReservationStatus.CANCELLED

    # Stock should be returned
    assert service.get_sku(sku_id)["quantity"] == 100


def test_cancel_confirmed_reservation_fails(service):
    sku_id = service.create_sku("Widget", 100)
    reservation_id = service.create_reservation(
        sku_id=sku_id,
        quantity=30,
        expires_in_seconds=3600,
        idempotency_key="key-1"
    )

    service.confirm_reservation(reservation_id)

    # Cannot cancel confirmed reservation
    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation_id)


def test_list_orders_pagination(service):
    sku_id = service.create_sku("Widget", 1000)

    # Create and confirm multiple reservations
    for i in range(30):
        reservation_id = service.create_reservation(
            sku_id=sku_id,
            quantity=10,
            expires_in_seconds=3600,
            idempotency_key=f"key-{i}"
        )
        service.confirm_reservation(reservation_id)

    # Test pagination
    orders, total = service.list_orders(skip=0, limit=10)
    assert len(orders) == 10
    assert total == 30

    orders, total = service.list_orders(skip=10, limit=10)
    assert len(orders) == 10

    orders, total = service.list_orders(skip=20, limit=10)
    assert len(orders) == 10

    orders, total = service.list_orders(skip=25, limit=10)
    assert len(orders) == 5
