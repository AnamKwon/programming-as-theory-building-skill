import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone

from commerce_service.models import Base, ReservationState
from commerce_service.service import (
    Commerce,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_create_sku_with_stock(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    sku = commerce.repo.get_sku("SKU001")
    assert sku is not None
    assert sku.name == "Widget"

    stock = commerce.repo.get_stock("SKU001")
    assert stock is not None
    assert stock.quantity == 100


def test_adjust_stock(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    commerce.adjust_stock("SKU001", 50)
    stock = commerce.repo.get_stock("SKU001")
    assert stock.quantity == 150

    commerce.adjust_stock("SKU001", -30)
    stock = commerce.repo.get_stock("SKU001")
    assert stock.quantity == 120


def test_reserve_success(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    result = commerce.reserve("SKU001", 50, "idempotency-key-1")
    assert result["reservation_id"] is not None
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 50
    assert result["state"] == ReservationState.PENDING
    assert result["is_new"] is True


def test_reserve_insufficient_stock(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=30)

    with pytest.raises(InsufficientStockError):
        commerce.reserve("SKU001", 50, "idempotency-key-1")


def test_reserve_idempotent(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    result1 = commerce.reserve("SKU001", 50, "idempotency-key-1")
    result2 = commerce.reserve("SKU001", 50, "idempotency-key-1")

    assert result1["reservation_id"] == result2["reservation_id"]
    assert result2["is_new"] is False


def test_confirm_reservation(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    res = commerce.reserve("SKU001", 50, "idempotency-key-1")
    result = commerce.confirm_reservation(res["reservation_id"])

    assert result["state"] == ReservationState.CONFIRMED
    assert result["order_id"] is not None

    # Stock should be deducted
    stock = commerce.repo.get_stock("SKU001")
    assert stock.quantity == 50


def test_confirm_expired_reservation(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    res = commerce.reserve("SKU001", 50, "idempotency-key-1", ttl_minutes=0)

    # Immediately try to confirm — should fail
    import time
    time.sleep(0.01)  # Tiny delay to ensure expiration

    with pytest.raises(ReservationExpiredError):
        commerce.confirm_reservation(res["reservation_id"])


def test_cancel_reservation(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    res = commerce.reserve("SKU001", 50, "idempotency-key-1")
    result = commerce.cancel_reservation(res["reservation_id"])

    assert result["state"] == ReservationState.CANCELLED


def test_cancel_already_confirmed_reservation(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=100)

    res = commerce.reserve("SKU001", 50, "idempotency-key-1")
    commerce.confirm_reservation(res["reservation_id"])

    with pytest.raises(InvalidStateTransitionError):
        commerce.cancel_reservation(res["reservation_id"])


def test_confirm_nonexistent_reservation(db):
    commerce = Commerce(db)

    with pytest.raises(ReservationNotFoundError):
        commerce.confirm_reservation("nonexistent-id")


def test_stock_cannot_go_negative(db):
    commerce = Commerce(db)
    commerce.create_sku("SKU001", "Widget", initial_stock=10)

    with pytest.raises(ValueError):
        commerce.adjust_stock("SKU001", -50)
