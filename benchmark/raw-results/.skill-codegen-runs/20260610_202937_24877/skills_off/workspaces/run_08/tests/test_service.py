import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta

from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateError,
    ReservationExpiredError,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def repository(temp_db):
    return Repository(f"sqlite:///{temp_db}")


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("PRODUCT-001", 100)
    assert result["sku"] == "PRODUCT-001"
    assert result["available_stock"] == 100


def test_adjust_stock(service):
    service.create_sku("PRODUCT-001", 100)
    result = service.adjust_stock("PRODUCT-001", -10)
    assert result.sku == "PRODUCT-001"
    assert result.available_stock == 90


def test_adjust_stock_not_found(service):
    with pytest.raises(ValueError):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    service.create_sku("PRODUCT-001", 100)
    reservation = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")
    assert reservation.sku == "PRODUCT-001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-key-1"

    sku = service.repo.get_sku("PRODUCT-001")
    assert sku.available_stock == 50


def test_create_reservation_insufficient_stock(service):
    service.create_sku("PRODUCT-001", 100)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("PRODUCT-001", 150, "idempotency-key-1")

    sku = service.repo.get_sku("PRODUCT-001")
    assert sku.available_stock == 100


def test_create_reservation_idempotency(service):
    service.create_sku("PRODUCT-001", 100)
    reservation1 = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")
    reservation2 = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")

    assert reservation1.id == reservation2.id
    assert reservation1.idempotency_key == reservation2.idempotency_key

    sku = service.repo.get_sku("PRODUCT-001")
    assert sku.available_stock == 50


def test_confirm_reservation_success(service):
    service.create_sku("PRODUCT-001", 100)
    reservation = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")

    reservation_response, order_response = service.confirm_reservation(reservation.id)

    assert reservation_response.status == "CONFIRMED"
    assert order_response.sku == "PRODUCT-001"
    assert order_response.quantity == 50


def test_confirm_reservation_expired(service):
    service.create_sku("PRODUCT-001", 100)
    reservation = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")

    reservation_model = service.repo.get_reservation(reservation.id)
    past_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    reservation_model.created_at = past_time
    session = service.repo.get_session()
    try:
        session.merge(reservation_model)
        session.commit()
    finally:
        session.close()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    updated_reservation = service.repo.get_reservation(reservation.id)
    assert updated_reservation.status == "EXPIRED"

    sku = service.repo.get_sku("PRODUCT-001")
    assert sku.available_stock == 100


def test_confirm_reservation_not_pending(service):
    service.create_sku("PRODUCT-001", 100)
    reservation = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")

    service.repo.update_reservation_status(reservation.id, "CANCELLED")

    with pytest.raises(InvalidStateError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(service):
    service.create_sku("PRODUCT-001", 100)
    reservation = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")

    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == "CANCELLED"

    sku = service.repo.get_sku("PRODUCT-001")
    assert sku.available_stock == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("PRODUCT-001", 100)
    reservation = service.create_reservation("PRODUCT-001", 50, "idempotency-key-1")

    service.repo.update_reservation_status(reservation.id, "CONFIRMED")

    with pytest.raises(InvalidStateError):
        service.cancel_reservation(reservation.id)


def test_get_orders_pagination(service):
    service.create_sku("PRODUCT-001", 100)
    for i in range(25):
        reservation = service.create_reservation("PRODUCT-001", 1, f"key-{i}")
        service.confirm_reservation(reservation.id)

    orders_page1, total1 = service.get_orders(page=1, size=10)
    orders_page2, total2 = service.get_orders(page=2, size=10)
    orders_page3, total3 = service.get_orders(page=3, size=10)

    assert len(orders_page1) == 10
    assert len(orders_page2) == 10
    assert len(orders_page3) == 5
    assert total1 == 25
    assert total2 == 25
    assert total3 == 25

    assert orders_page1[0].id != orders_page2[0].id
    assert orders_page2[0].id != orders_page3[0].id
