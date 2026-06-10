import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    response = service.create_sku("SKU001", "Widget", 100)
    assert response.id == "SKU001"
    assert response.name == "Widget"
    assert response.available_stock == 100
    assert response.reserved_stock == 0


def test_adjust_stock_positive(service):
    service.create_sku("SKU001", "Widget", 100)
    response = service.adjust_stock("SKU001", 50)
    assert response.available_stock == 150


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", "Widget", 100)
    response = service.adjust_stock("SKU001", -30)
    assert response.available_stock == 70


def test_adjust_stock_insufficient(service):
    service.create_sku("SKU001", "Widget", 100)
    with pytest.raises(InsufficientStockError):
        service.adjust_stock("SKU001", -150)


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Widget", 100)
    response = service.create_reservation("SKU001", 30, 30)

    assert response.sku_id == "SKU001"
    assert response.quantity == 30
    assert response.status.value == "pending"
    assert response.expires_at > datetime.utcnow()


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Widget", 20)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 50, 30)


def test_create_reservation_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.create_reservation("NONEXISTENT", 10, 30)


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", "Widget", 100)
    reservation = service.create_reservation("SKU001", 30, 30)

    confirmed_res, order_id = service.confirm_reservation(
        reservation.id, "idempotency-key-1"
    )

    assert confirmed_res.status.value == "confirmed"
    assert order_id is not None


def test_confirm_reservation_idempotency(service):
    service.create_sku("SKU001", "Widget", 100)
    reservation = service.create_reservation("SKU001", 30, 30)

    _, order_id_1 = service.confirm_reservation(
        reservation.id, "idempotency-key-1"
    )

    # Fetch the reservation again (already confirmed)
    from commerce_service.repository import Repository
    repo = Repository(service.repo.db)
    res = repo.get_reservation(reservation.id)

    _, order_id_2 = service.confirm_reservation(
        reservation.id, "idempotency-key-1"
    )

    assert order_id_1 == order_id_2


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("NONEXISTENT", "idempotency-key-1")


def test_confirm_expired_reservation(service):
    service.create_sku("SKU001", "Widget", 100)

    from commerce_service.repository import Repository
    from commerce_service.models import ReservationStatus

    repo = Repository(service.repo.db)
    reservation_id = "RES001"
    expires_at = datetime.utcnow() - timedelta(minutes=1)
    repo.create_reservation(reservation_id, "SKU001", 30, expires_at)
    repo.update_sku_stock("SKU001", -30, 30)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation_id, "idempotency-key-1")


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Widget", 100)
    reservation = service.create_reservation("SKU001", 30, 30)

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status.value == "cancelled"


def test_cancel_reservation_returns_stock(service):
    service.create_sku("SKU001", "Widget", 100)
    sku_before = service.repo.get_sku("SKU001")
    assert sku_before.available_stock == 100
    assert sku_before.reserved_stock == 0

    reservation = service.create_reservation("SKU001", 30, 30)

    sku_after_reserve = service.repo.get_sku("SKU001")
    assert sku_after_reserve.available_stock == 70
    assert sku_after_reserve.reserved_stock == 30

    service.cancel_reservation(reservation.id)

    sku_after_cancel = service.repo.get_sku("SKU001")
    assert sku_after_cancel.available_stock == 100
    assert sku_after_cancel.reserved_stock == 0


def test_cleanup_expired_reservations(service):
    service.create_sku("SKU001", "Widget", 100)
    service.create_sku("SKU002", "Gadget", 50)

    from commerce_service.repository import Repository
    repo = Repository(service.repo.db)

    # Create an expired reservation
    expired_res_id = "RES001"
    expires_at = datetime.utcnow() - timedelta(minutes=1)
    repo.create_reservation(expired_res_id, "SKU001", 20, expires_at)
    repo.update_sku_stock("SKU001", -20, 20)

    # Create an active reservation (not expired)
    active_res = service.create_reservation("SKU002", 10, 30)

    cleaned = service.cleanup_expired_reservations()
    assert cleaned == 1

    # Check expired reservation was cancelled and stock returned
    expired_res = repo.get_reservation(expired_res_id)
    assert expired_res.status == "cancelled"

    sku001 = repo.get_sku("SKU001")
    assert sku001.available_stock == 100
    assert sku001.reserved_stock == 0

    # Check active reservation is untouched
    sku002 = repo.get_sku("SKU002")
    assert sku002.available_stock == 40
    assert sku002.reserved_stock == 10


def test_list_orders(service):
    service.create_sku("SKU001", "Widget", 100)
    reservation = service.create_reservation("SKU001", 30, 30)
    service.confirm_reservation(reservation.id, "idempotency-key-1")

    result = service.list_orders(skip=0, limit=10)
    assert result["total"] == 1
    assert len(result["orders"]) == 1
    assert result["orders"][0].quantity == 30


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Widget", 100)

    for i in range(25):
        reservation = service.create_reservation("SKU001", 1, 30)
        service.confirm_reservation(reservation.id, f"idempotency-key-{i}")

    result1 = service.list_orders(skip=0, limit=10)
    assert len(result1["orders"]) == 10
    assert result1["total"] == 25

    result2 = service.list_orders(skip=10, limit=10)
    assert len(result2["orders"]) == 10

    result3 = service.list_orders(skip=20, limit=10)
    assert len(result3["orders"]) == 5
