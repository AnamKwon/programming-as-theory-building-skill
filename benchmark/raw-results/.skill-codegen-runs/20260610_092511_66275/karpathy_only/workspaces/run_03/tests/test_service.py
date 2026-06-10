import os
import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    InsufficientStockError,
    ReservationAlreadyProcessedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
)


@pytest.fixture
def temp_db():
    _, path = tempfile.mkstemp(suffix=".db")
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def repository(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    return Service(repository)


def test_create_sku(service):
    assert service.create_sku("SKU001", "Widget", 100)
    assert not service.create_sku("SKU001", "Widget", 100)


def test_adjust_stock(service, repository):
    service.create_sku("SKU001", "Widget", 100)
    service.adjust_stock("SKU001", 50)
    sku = repository.get_sku("SKU001")
    assert sku["available_stock"] == 150


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Widget", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-key-1")
    assert result["sku"] == "SKU001"
    assert result["quantity"] == 10
    assert result["status"] == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Widget", 5)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 10, "idempotency-key-1")


def test_create_reservation_idempotent(service):
    service.create_sku("SKU001", "Widget", 100)
    result1 = service.create_reservation("SKU001", 10, "idempotency-key-1")
    result2 = service.create_reservation("SKU001", 10, "idempotency-key-1")
    assert result1["reservation_id"] == result2["reservation_id"]


def test_create_reservation_idempotent_already_confirmed(service):
    service.create_sku("SKU001", "Widget", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-key-1")
    reservation_id = result["reservation_id"]
    service.confirm_reservation(reservation_id)

    with pytest.raises(ReservationAlreadyProcessedError):
        service.create_reservation("SKU001", 10, "idempotency-key-1")


def test_confirm_reservation_success(service, repository):
    service.create_sku("SKU001", "Widget", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-key-1")
    reservation_id = res["reservation_id"]

    order = service.confirm_reservation(reservation_id)
    assert order["sku"] == "SKU001"
    assert order["quantity"] == 10
    assert order["status"] == "completed"

    sku = repository.get_sku("SKU001")
    assert sku["available_stock"] == 90
    assert sku["reserved_stock"] == 0


def test_confirm_reservation_idempotent(service):
    service.create_sku("SKU001", "Widget", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-key-1")
    reservation_id = res["reservation_id"]

    order1 = service.confirm_reservation(reservation_id)
    order2 = service.confirm_reservation(reservation_id)
    assert order1["order_id"] == order2["order_id"]


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("nonexistent-id")


def test_confirm_reservation_expired(service, repository):
    service.create_sku("SKU001", "Widget", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-key-1")
    reservation_id = res["reservation_id"]

    # Set reservation to expired manually
    now = datetime.utcnow()
    past = (now - timedelta(minutes=5)).isoformat()
    conn = repository._get_connection()
    conn.execute(
        "UPDATE reservations SET expires_at = ? WHERE id = ?", (past, reservation_id)
    )
    conn.commit()
    conn.close()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation_id)

    # Verify reservation was marked as expired
    reservation = repository.get_reservation(reservation_id)
    assert reservation["status"] == ReservationStatus.EXPIRED.value

    # Verify stock was released
    sku = repository.get_sku("SKU001")
    assert sku["available_stock"] == 100
    assert sku["reserved_stock"] == 0


def test_cancel_reservation_success(service, repository):
    service.create_sku("SKU001", "Widget", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-key-1")
    reservation_id = res["reservation_id"]

    service.cancel_reservation(reservation_id)

    reservation = repository.get_reservation(reservation_id)
    assert reservation["status"] == ReservationStatus.CANCELLED.value

    sku = repository.get_sku("SKU001")
    assert sku["available_stock"] == 100
    assert sku["reserved_stock"] == 0


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("nonexistent-id")


def test_cancel_reservation_idempotent(service):
    service.create_sku("SKU001", "Widget", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-key-1")
    reservation_id = res["reservation_id"]

    service.cancel_reservation(reservation_id)
    service.cancel_reservation(reservation_id)
