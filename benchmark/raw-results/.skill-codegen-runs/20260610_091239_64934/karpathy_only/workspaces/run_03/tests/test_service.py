import pytest
import tempfile
from pathlib import Path

from commerce_service.models import ReservationStatus, OrderStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)


@pytest.fixture
def repo():
    tmpdir = tempfile.mkdtemp()
    db_path = str(Path(tmpdir) / "test.db")
    repo = Repository(db_path=db_path)
    yield repo
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def service(repo):
    return Service(repo)


def test_create_sku(service):
    sku = service.create_sku("SKU001", "Widget A", 100)
    assert sku.sku_id == "SKU001"
    assert sku.name == "Widget A"
    assert sku.total_stock == 100
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_adjust_stock(service):
    service.create_sku("SKU001", "Widget A", 100)
    sku = service.adjust_stock("SKU001", 50)
    assert sku.total_stock == 150
    assert sku.available_stock == 150


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Widget A", 100)
    res = service.create_reservation("SKU001", 30)

    assert res.sku_id == "SKU001"
    assert res.quantity == 30
    assert res.status == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Widget A", 100)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 150)


def test_create_reservation_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.create_reservation("NONEXISTENT", 10)


def test_idempotent_reservation(service):
    service.create_sku("SKU001", "Widget A", 100)
    res1 = service.create_reservation("SKU001", 30, idempotency_key="key1")
    res2 = service.create_reservation("SKU001", 30, idempotency_key="key1")

    assert res1.reservation_id == res2.reservation_id
    assert res1.quantity == res2.quantity


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Widget A", 100)
    res = service.create_reservation("SKU001", 30)
    confirmed = service.confirm_reservation(res.reservation_id)

    assert confirmed.status == ReservationStatus.CONFIRMED
    assert confirmed.confirmed_at is not None


def test_confirm_nonexistent_reservation(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("NONEXISTENT")


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Widget A", 100)
    res = service.create_reservation("SKU001", 30)
    cancelled = service.cancel_reservation(res.reservation_id)

    assert cancelled.status == ReservationStatus.CANCELLED
    assert cancelled.cancelled_at is not None


def test_cancel_nonexistent_reservation(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("NONEXISTENT")


def test_reserved_stock_counted(service):
    service.create_sku("SKU001", "Widget A", 100)
    service.create_reservation("SKU001", 30)

    sku = service._get_sku_response("SKU001")
    assert sku.available_stock == 70
    assert sku.reserved_stock == 30


def test_multiple_reservations_share_stock(service):
    service.create_sku("SKU001", "Widget A", 100)
    service.create_reservation("SKU001", 50)

    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 60)


def test_get_orders_empty(service):
    orders, total = service.get_orders()
    assert orders == []
    assert total == 0


def test_get_orders_pagination(service):
    service.create_sku("SKU001", "Widget A", 100)
    repo = service.repo

    for i in range(15):
        repo.create_order(f"ORDER{i:03d}", [])

    page1, total = service.get_orders(offset=0, limit=10)
    assert len(page1) == 10
    assert total == 15

    page2, total = service.get_orders(offset=10, limit=10)
    assert len(page2) == 5
    assert total == 15
