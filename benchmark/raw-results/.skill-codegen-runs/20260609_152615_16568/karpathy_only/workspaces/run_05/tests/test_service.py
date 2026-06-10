import pytest
from datetime import datetime, timedelta

from commerce_service.models import OrderStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    DuplicateReservationError,
    InsufficientStockError,
    ReservationExpiredError,
    Service,
)


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def svc(repo):
    return Service(repo)


def test_create_sku(svc):
    result = svc.create_sku("SKU-001", 100)
    assert result["sku_id"] == "SKU-001"
    assert result["available_stock"] == 100


def test_adjust_stock(svc):
    svc.create_sku("SKU-001", 100)
    result = svc.adjust_stock("SKU-001", 50)
    assert result["available_stock"] == 150

    result = svc.adjust_stock("SKU-001", -30)
    assert result["available_stock"] == 120


def test_create_reservation_success(svc):
    svc.create_sku("SKU-001", 100)
    result = svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    assert result["sku_id"] == "SKU-001"
    assert result["quantity"] == 50
    assert result["status"] == OrderStatus.RESERVED.value


def test_create_reservation_insufficient_stock(svc):
    svc.create_sku("SKU-001", 50)
    with pytest.raises(InsufficientStockError):
        svc.create_reservation("SKU-001", 100, "idem-key-1", 3600)


def test_create_reservation_idempotent(svc):
    svc.create_sku("SKU-001", 100)
    result1 = svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    result2 = svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    assert result1["reservation_id"] == result2["reservation_id"]


def test_create_reservation_duplicate_key_raises_error(svc):
    svc.create_sku("SKU-001", 100)
    svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    with pytest.raises(DuplicateReservationError):
        svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)


def test_confirm_reservation_success(svc, repo):
    svc.create_sku("SKU-001", 100)
    res = svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    reservation_id = res["reservation_id"]

    order = svc.confirm_reservation(reservation_id)
    assert order["sku_id"] == "SKU-001"
    assert order["quantity"] == 50
    assert order["status"] == OrderStatus.CONFIRMED.value


def test_confirm_reservation_expired(svc, repo):
    svc.create_sku("SKU-001", 100)
    res = svc.create_reservation("SKU-001", 50, "idem-key-1", 1)
    reservation_id = res["reservation_id"]

    # Expire the reservation by setting its expiry to the past
    reservation = repo.get_reservation(reservation_id)
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    repo.db.commit()

    with pytest.raises(ReservationExpiredError):
        svc.confirm_reservation(reservation_id)


def test_cancel_reservation(svc, repo):
    svc.create_sku("SKU-001", 100)
    res = svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    reservation_id = res["reservation_id"]

    svc.cancel_reservation(reservation_id)
    assert repo.get_reservation(reservation_id) is None


def test_list_orders(svc):
    svc.create_sku("SKU-001", 100)
    res = svc.create_reservation("SKU-001", 50, "idem-key-1", 3600)
    svc.confirm_reservation(res["reservation_id"])

    result = svc.list_orders(limit=10, offset=0)
    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["quantity"] == 50


def test_list_orders_pagination(svc):
    svc.create_sku("SKU-001", 100)
    for i in range(5):
        res = svc.create_reservation("SKU-001", 10, f"idem-key-{i}", 3600)
        svc.confirm_reservation(res["reservation_id"])

    result = svc.list_orders(limit=2, offset=0)
    assert result["total"] == 5
    assert len(result["items"]) == 2
    assert result["limit"] == 2
    assert result["offset"] == 0

    result2 = svc.list_orders(limit=2, offset=2)
    assert len(result2["items"]) == 2
    assert result2["offset"] == 2


def test_multiple_reservations_same_sku(svc):
    svc.create_sku("SKU-001", 100)
    res1 = svc.create_reservation("SKU-001", 30, "idem-key-1", 3600)
    res2 = svc.create_reservation("SKU-001", 40, "idem-key-2", 3600)

    assert res1["status"] == OrderStatus.RESERVED.value
    assert res2["status"] == OrderStatus.RESERVED.value

    with pytest.raises(InsufficientStockError):
        svc.create_reservation("SKU-001", 40, "idem-key-3", 3600)
