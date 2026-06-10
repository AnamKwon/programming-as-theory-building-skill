import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    SKUNotFoundError,
)
from commerce_service.models import ReservationState


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", "Test Product")
    assert result["id"] > 0
    assert result["sku_code"] == "SKU001"
    assert result["name"] == "Test Product"


def test_adjust_stock_increase(service):
    service.create_sku("SKU001", "Test Product")
    result = service.adjust_stock(1, Decimal("100"))
    assert result["available"] == 100.0
    assert result["reserved"] == 0.0


def test_adjust_stock_decrease(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    result = service.adjust_stock(1, Decimal("-30"))
    assert result["available"] == 70.0


def test_adjust_stock_negative_error(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("50"))
    with pytest.raises(ValueError):
        service.adjust_stock(1, Decimal("-100"))


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    result = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    assert result["id"] > 0
    assert result["state"] == ReservationState.PENDING
    assert result["quantity"] == 30.0


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("50"))
    with pytest.raises(InsufficientStockError):
        service.create_reservation(1, Decimal("100"), "idempotency-key-1")


def test_create_reservation_idempotent(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    result1 = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    result2 = service.create_reservation(1, Decimal("50"), "idempotency-key-1")
    assert result1["id"] == result2["id"]
    assert result2["quantity"] == 30.0


def test_create_reservation_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.create_reservation(999, Decimal("10"), "idempotency-key-1")


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    res = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    result = service.confirm_reservation(res["id"])
    assert result["state"] == ReservationState.CONFIRMED


def test_confirm_reservation_not_found(service):
    with pytest.raises(Exception):
        service.confirm_reservation(999)


def test_confirm_already_confirmed(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    res = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    service.confirm_reservation(res["id"])
    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(res["id"])


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    res = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    result = service.cancel_reservation(res["id"])
    assert result["state"] == ReservationState.CANCELLED


def test_cancel_already_cancelled(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    res = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    service.cancel_reservation(res["id"])
    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(res["id"])


def test_reservation_expiration_on_confirm(service):
    # Create a reservation and manually set it to expired
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))
    res = service.create_reservation(1, Decimal("30"), "idempotency-key-1")

    # Manually expire the reservation by directly updating the database
    session = service.repo.get_session()
    try:
        from commerce_service.models import Reservation
        reservation = session.query(Reservation).filter(Reservation.id == res["id"]).first()
        reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(res["id"])


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("1000"))

    # Create and confirm multiple reservations
    for i in range(15):
        res = service.create_reservation(1, Decimal("10"), f"key-{i}")
        service.confirm_reservation(res["id"])

    result = service.list_orders(limit=10, offset=0)
    assert result["total"] == 15
    assert len(result["items"]) == 10
    assert result["limit"] == 10
    assert result["offset"] == 0

    result2 = service.list_orders(limit=10, offset=10)
    assert len(result2["items"]) == 5


def test_stock_reserved_released_on_cancel(service):
    service.create_sku("SKU001", "Test Product")
    service.adjust_stock(1, Decimal("100"))

    res = service.create_reservation(1, Decimal("30"), "idempotency-key-1")
    stock = service.repo.get_stock(1)
    assert stock.available == Decimal("70")
    assert stock.reserved == Decimal("30")

    service.cancel_reservation(res["id"])
    stock = service.repo.get_stock(1)
    assert stock.available == Decimal("100")
    assert stock.reserved == Decimal("0")
