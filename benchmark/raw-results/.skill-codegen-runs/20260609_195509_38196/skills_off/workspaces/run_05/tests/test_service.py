import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    ExpiredReservationError,
    InsufficientStockError,
    InvalidReservationStateError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repository):
    return CommerceService(repository, reservation_ttl_minutes=15)


def test_create_sku(service):
    result = service.create_sku("SKU001", initial_stock=100)
    assert result["sku_id"] == "SKU001"
    assert result["stock_level"] == 100
    assert "created_at" in result


def test_adjust_stock_positive(service):
    service.create_sku("SKU001", initial_stock=100)
    result = service.adjust_stock("SKU001", quantity_delta=50)
    assert result["stock_level"] == 150


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", initial_stock=100)
    result = service.adjust_stock("SKU001", quantity_delta=-30)
    assert result["stock_level"] == 70


def test_adjust_stock_below_zero_raises(service):
    service.create_sku("SKU001", initial_stock=50)
    with pytest.raises(ValueError, match="Stock cannot be negative"):
        service.adjust_stock("SKU001", quantity_delta=-100)


def test_create_reservation_success(service):
    service.create_sku("SKU001", initial_stock=100)
    result, was_cached = service.create_reservation("SKU001", 20, "idempotency-1")
    assert result["reservation_id"]
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 20
    assert not was_cached


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", initial_stock=10)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 20, "idempotency-1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", initial_stock=100)
    result1, was_cached1 = service.create_reservation("SKU001", 20, "idempotency-1")
    result2, was_cached2 = service.create_reservation("SKU001", 20, "idempotency-1")
    assert result1["reservation_id"] == result2["reservation_id"]
    assert not was_cached1
    assert was_cached2


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", initial_stock=100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-1")
    order = service.confirm_reservation(reservation["reservation_id"])
    assert order["order_id"]
    assert order["confirmed_at"]


def test_confirm_reservation_expired(service, repository):
    service.create_sku("SKU001", initial_stock=100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-1")

    expired_reservation = repository.get_reservation(reservation["reservation_id"])
    expired_reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    repository.session.commit()

    with pytest.raises(ExpiredReservationError):
        service.confirm_reservation(reservation["reservation_id"])


def test_confirm_already_confirmed_raises(service):
    service.create_sku("SKU001", initial_stock=100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-1")
    service.confirm_reservation(reservation["reservation_id"])

    with pytest.raises(InvalidReservationStateError):
        service.confirm_reservation(reservation["reservation_id"])


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", initial_stock=100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-1")
    result = service.cancel_reservation(reservation["reservation_id"])
    assert result["reservation_id"] == reservation["reservation_id"]


def test_cancel_already_confirmed_raises(service):
    service.create_sku("SKU001", initial_stock=100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-1")
    service.confirm_reservation(reservation["reservation_id"])

    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation["reservation_id"])


def test_get_orders_pagination(service):
    service.create_sku("SKU001", initial_stock=1000)
    for i in range(15):
        res, _ = service.create_reservation("SKU001", 10, f"idempotency-{i}")
        service.confirm_reservation(res["reservation_id"])

    result = service.get_orders(limit=10)
    assert len(result["orders"]) == 10
    assert result["has_more"] is True
    assert result["next_cursor"] is not None

    result2 = service.get_orders(limit=10, cursor=result["next_cursor"])
    assert len(result2["orders"]) == 5
    assert result2["has_more"] is False
    assert result2["next_cursor"] is None
