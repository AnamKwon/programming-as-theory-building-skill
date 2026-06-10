import os
import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.models import CreateReservationRequest, CreateSKURequest
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateError,
    ReservationExpiredError,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repository(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    request = CreateSKURequest(sku="SKU001", initial_stock=100)
    response = service.create_sku(request)
    assert response.sku == "SKU001"
    assert response.available_stock == 100
    assert response.id is not None


def test_adjust_stock(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    response = service.adjust_stock("SKU001", 50)
    assert response.sku == "SKU001"
    assert response.available_stock == 150

    response = service.adjust_stock("SKU001", -30)
    assert response.available_stock == 120


def test_create_reservation_happy_path(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")
    response = service.create_reservation(request)
    assert response.sku == "SKU001"
    assert response.quantity == 50
    assert response.status == "PENDING"
    assert response.idempotency_key == "key1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=50))
    request = CreateReservationRequest(sku="SKU001", quantity=100, idempotency_key="key1")
    with pytest.raises(InsufficientStockError):
        service.create_reservation(request)


def test_create_reservation_idempotency(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")

    response1 = service.create_reservation(request)
    response2 = service.create_reservation(request)

    assert response1.id == response2.id
    assert response1.sku == response2.sku
    assert response1.quantity == response2.quantity

    sku_obj = service.repository.get_sku_by_name("SKU001")
    assert sku_obj.available_stock == 50


def test_confirm_reservation_happy_path(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")
    reservation = service.create_reservation(request)

    response = service.confirm_reservation(reservation.id)
    assert response.status == "CONFIRMED"

    orders, total = service.repository.get_orders(1, 10)
    assert len(orders) == 1
    assert orders[0].sku == "SKU001"
    assert orders[0].quantity == 50


def test_confirm_reservation_not_pending(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")
    reservation = service.create_reservation(request)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateError):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_expired(service, repository):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")
    reservation = service.create_reservation(request)

    reservation_obj = repository.get_reservation_by_id(reservation.id)
    reservation_obj.created_at = datetime.utcnow() - timedelta(seconds=301)

    session = repository.get_session()
    session.merge(reservation_obj)
    session.commit()
    session.close()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)

    updated_reservation = repository.get_reservation_by_id(reservation.id)
    assert updated_reservation.status == "EXPIRED"

    sku_obj = repository.get_sku_by_name("SKU001")
    assert sku_obj.available_stock == 100


def test_cancel_reservation(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")
    reservation = service.create_reservation(request)

    response = service.cancel_reservation(reservation.id)
    assert response.status == "CANCELLED"

    sku_obj = service.repository.get_sku_by_name("SKU001")
    assert sku_obj.available_stock == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))
    request = CreateReservationRequest(sku="SKU001", quantity=50, idempotency_key="key1")
    reservation = service.create_reservation(request)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidStateError):
        service.cancel_reservation(reservation.id)


def test_get_orders(service):
    service.create_sku(CreateSKURequest(sku="SKU001", initial_stock=100))

    for i in range(15):
        request = CreateReservationRequest(sku="SKU001", quantity=1, idempotency_key=f"key{i}")
        reservation = service.create_reservation(request)
        service.confirm_reservation(reservation.id)

    response = service.get_orders(page=1, size=10)
    assert len(response.items) == 10
    assert response.page == 1
    assert response.size == 10
    assert response.total == 15

    response = service.get_orders(page=2, size=10)
    assert len(response.items) == 5
    assert response.page == 2
