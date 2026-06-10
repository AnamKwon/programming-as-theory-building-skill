import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidReservationStateError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repository(db):
    return Repository(db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("SKU001", "Test Product", 100)
    assert result["product_id"] == "SKU001"
    assert result["name"] == "Test Product"
    assert result["current_stock"] == 100


def test_adjust_stock(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.adjust_stock("SKU001", 50)
    assert result["current_stock"] == 150

    result = service.adjust_stock("SKU001", -30)
    assert result["current_stock"] == 120


def test_adjust_stock_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    assert result["product_id"] == "SKU001"
    assert result["quantity"] == 10
    assert result["status"] == "pending"
    assert result["id"] is not None


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Test Product", 5)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 10, "idempotency-1")


def test_create_reservation_sku_not_found(service):
    with pytest.raises(SKUNotFoundError):
        service.create_reservation("NONEXISTENT", 10, "idempotency-1")


def test_idempotent_reservation_retry(service):
    service.create_sku("SKU001", "Test Product", 100)
    result1 = service.create_reservation("SKU001", 10, "idempotency-key-1")
    result2 = service.create_reservation("SKU001", 20, "idempotency-key-1")
    assert result1["id"] == result2["id"]
    assert result1["quantity"] == result2["quantity"]
    assert result2["quantity"] == 10


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    reservation_id = result["id"]

    confirmed = service.confirm_reservation(reservation_id)
    assert confirmed["status"] == "confirmed"

    # Check stock was reduced
    repo = service.repo
    sku = repo.get_sku("SKU001")
    assert sku.current_stock == 90


def test_confirm_expired_reservation(service, repository):
    from datetime import timedelta
    service.create_sku("SKU001", "Test Product", 100)

    # Create a reservation with past expiry
    res_id = "test-res-1"
    expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    repository.create_reservation(res_id, "SKU001", 10, "idempotency-1", expires_at)

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(res_id)


def test_confirm_invalid_state(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    reservation_id = result["id"]

    # Confirm once
    service.confirm_reservation(reservation_id)

    # Try to confirm again
    with pytest.raises(InvalidReservationStateError):
        service.confirm_reservation(reservation_id)


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    reservation_id = result["id"]

    cancelled = service.cancel_reservation(reservation_id)
    assert cancelled["status"] == "cancelled"


def test_cancel_already_cancelled(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    reservation_id = result["id"]

    service.cancel_reservation(reservation_id)
    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation_id)


def test_cancel_confirmed_reservation(service):
    service.create_sku("SKU001", "Test Product", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    reservation_id = result["id"]

    service.confirm_reservation(reservation_id)
    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation_id)


def test_list_orders(service):
    service.create_sku("SKU001", "Test Product", 100)
    service.create_sku("SKU002", "Test Product 2", 50)

    service.create_reservation("SKU001", 10, "idempotency-1")
    service.create_reservation("SKU002", 5, "idempotency-2")

    result = service.list_orders(limit=10, offset=0)
    assert result["total"] == 2
    assert len(result["orders"]) == 2
    assert result["limit"] == 10
    assert result["offset"] == 0


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Test Product", 100)

    for i in range(15):
        service.create_reservation("SKU001", 1, f"idempotency-{i}")

    result = service.list_orders(limit=5, offset=0)
    assert result["total"] == 15
    assert len(result["orders"]) == 5

    result = service.list_orders(limit=5, offset=5)
    assert len(result["orders"]) == 5

    result = service.list_orders(limit=5, offset=10)
    assert len(result["orders"]) == 5
