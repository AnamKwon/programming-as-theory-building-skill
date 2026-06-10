import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    sku = service.create_sku("PROD-001", "Test Product")
    assert sku.id is not None
    assert sku.sku_code == "PROD-001"
    assert sku.name == "Test Product"
    assert sku.available_quantity == 0


def test_adjust_stock(service):
    sku = service.create_sku("PROD-001", "Test Product")
    updated = service.adjust_stock(sku.id, 100)
    assert updated.available_quantity == 100


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock(999, 10)


def test_create_reservation_happy_path(service, repo):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 50)

    order = service.create_reservation(sku.id, 10, "idempotency-key-1")
    assert order.id is not None
    assert order.status == "reserved"
    assert order.quantity == 10

    updated_sku = repo.get_sku(sku.id)
    assert updated_sku.available_quantity == 40
    assert updated_sku.reserved_quantity == 10


def test_create_reservation_insufficient_stock(service, repo):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 10, "idempotency-key-1")


def test_create_reservation_idempotent_retry(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 50)

    order1 = service.create_reservation(sku.id, 10, "idempotency-key-1")
    order2 = service.create_reservation(sku.id, 10, "idempotency-key-1")

    assert order1.id == order2.id


def test_confirm_reservation(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 50)

    order = service.create_reservation(sku.id, 10, "idempotency-key-1")
    confirmed = service.confirm_reservation(order.id)

    assert confirmed.status == "confirmed"
    assert confirmed.expires_at is None


def test_confirm_expired_reservation(service, repo):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 50)

    order = service.create_reservation(sku.id, 10, "idempotency-key-1")

    with repo.get_session() as session:
        db_order = session.query(repo.Order).filter(repo.Order.id == order.id).first()
        db_order.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(order.id)


def test_cancel_reserved_order(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 50)

    order = service.create_reservation(sku.id, 10, "idempotency-key-1")
    cancelled = service.cancel_reservation(order.id)

    assert cancelled.status == "cancelled"

    updated_sku = service.repo.get_sku(sku.id)
    assert updated_sku.available_quantity == 50
    assert updated_sku.reserved_quantity == 0


def test_cancel_confirmed_order_fails(service):
    sku = service.create_sku("PROD-001", "Test Product")
    service.adjust_stock(sku.id, 50)

    order = service.create_reservation(sku.id, 10, "idempotency-key-1")
    service.confirm_reservation(order.id)

    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(order.id)
