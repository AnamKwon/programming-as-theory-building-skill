import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus, OrderStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
    IdempotencyKeyExistsError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku_success(service):
    result = service.create_sku("SKU001", "Product 1", "Description 1")
    assert result["sku_code"] == "SKU001"
    assert result["name"] == "Product 1"
    assert result["description"] == "Description 1"


def test_create_sku_duplicate_fails(service):
    service.create_sku("SKU001", "Product 1", None)
    with pytest.raises(ValueError, match="SKU already exists"):
        service.create_sku("SKU001", "Product 2", None)


def test_adjust_stock_success(service):
    service.create_sku("SKU001", "Product 1", None)
    result = service.adjust_stock("SKU001", 100)
    assert result.available == 100
    assert result.reserved == 0


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("SKU001", 100)


def test_adjust_stock_negative_fails(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 50)
    with pytest.raises(InsufficientStockError):
        service.adjust_stock("SKU001", -100)


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    result = service.create_reservation("SKU001", 10)
    assert result.id
    assert result.sku_code == "SKU001"
    assert result.quantity == 10
    assert result.status == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 10)


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(SKUNotFoundError):
        service.create_reservation("SKU001", 10)


def test_create_reservation_with_idempotency_key(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    result1 = service.create_reservation(
        "SKU001", 10, idempotency_key="key-001"
    )
    result2 = service.create_reservation(
        "SKU001", 10, idempotency_key="key-001"
    )

    assert result1.id == result2.id
    assert result1.quantity == result2.quantity


def test_create_reservation_expired_idempotency_key_fails(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    result = service.create_reservation(
        "SKU001", 10, idempotency_key="key-001"
    )

    service.repo.update_reservation_status(
        result.id, ReservationStatus.EXPIRED
    )
    service.repo.commit()

    with pytest.raises(IdempotencyKeyExistsError):
        service.create_reservation(
            "SKU001", 10, idempotency_key="key-001"
        )


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    confirmed_reservation, order = service.confirm_reservation(reservation.id)

    assert confirmed_reservation.status == ReservationStatus.CONFIRMED
    assert order["status"] == OrderStatus.PENDING
    assert order["sku_code"] == "SKU001"
    assert order["quantity"] == 10


def test_confirm_reservation_expired_fails(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10, reservation_duration_seconds=1)

    import time
    time.sleep(2)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_nonexistent_fails(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_confirm_reservation_already_confirmed_fails(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="Cannot confirm reservation"):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    result = service.cancel_reservation(reservation.id)

    assert result.status == ReservationStatus.CANCELLED
    stock = service.repo.get_stock("SKU001")
    assert stock.available == 100
    assert stock.reserved == 0


def test_cancel_reservation_nonexistent_fails(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(999)


def test_cancel_reservation_confirmed_fails(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="Cannot cancel reservation"):
        service.cancel_reservation(reservation.id)


def test_get_order_success(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 100)

    reservation = service.create_reservation("SKU001", 10)
    _, order = service.confirm_reservation(reservation.id)

    result = service.get_order(order["id"])
    assert result["id"] == order["id"]
    assert result["sku_code"] == "SKU001"


def test_get_order_nonexistent_fails(service):
    with pytest.raises(ValueError, match="Order not found"):
        service.get_order(999)


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Product 1", None)
    service.adjust_stock("SKU001", 1000)

    for i in range(5):
        reservation = service.create_reservation("SKU001", 10)
        service.confirm_reservation(reservation.id)

    result = service.list_orders(offset=0, limit=3)
    assert len(result["orders"]) == 3
    assert result["total"] == 5
    assert result["offset"] == 0
    assert result["limit"] == 3

    result = service.list_orders(offset=3, limit=3)
    assert len(result["orders"]) == 2
