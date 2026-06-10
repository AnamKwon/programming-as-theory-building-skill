import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommercialService,
    ConflictError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def service(repo):
    return CommercialService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", "Product A", "A test product")
    assert result["id"] == "SKU001"
    assert result["name"] == "Product A"
    assert result["description"] == "A test product"
    assert result["created_at"] is not None


def test_adjust_stock(service):
    service.create_sku("SKU001", "Product A", None)
    result = service.adjust_stock("SKU001", 100)
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 100

    result = service.adjust_stock("SKU001", 50)
    assert result["quantity"] == 150


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    result = service.create_reservation("SKU001", 50, "idempotency-1", 3600)
    assert result["id"] is not None
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 50
    assert result["status"] == "pending"
    assert result["idempotency_key"] == "idempotency-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 30)

    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 50, "idempotency-1", 3600)


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    res1 = service.create_reservation("SKU001", 50, "idempotency-1", 3600)
    res2 = service.create_reservation("SKU001", 50, "idempotency-1", 3600)

    assert res1["id"] == res2["id"]
    assert res1["idempotency_key"] == res2["idempotency_key"]


def test_create_reservation_idempotency_conflict_on_expired(service, repo):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    res1 = service.create_reservation("SKU001", 50, "idempotency-1", 1)
    repo.mark_expired_reservations()

    with pytest.raises(ConflictError, match="expired reservation"):
        service.create_reservation("SKU001", 50, "idempotency-1", 3600)


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    res = service.create_reservation("SKU001", 50, "idempotency-1", 3600)
    confirmed = service.confirm_reservation(res["id"])

    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_at"] is not None


def test_confirm_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("non-existent-id")


def test_confirm_reservation_expired(service, repo):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    res = service.create_reservation("SKU001", 50, "idempotency-1", 1)
    repo.mark_expired_reservations()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(res["id"])


def test_confirm_reservation_already_confirmed(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    res = service.create_reservation("SKU001", 50, "idempotency-1", 3600)
    service.confirm_reservation(res["id"])

    with pytest.raises(ConflictError, match="confirmed"):
        service.confirm_reservation(res["id"])


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 100)

    res = service.create_reservation("SKU001", 50, "idempotency-1", 3600)
    cancelled = service.cancel_reservation(res["id"])

    assert cancelled["status"] == "cancelled"


def test_cancel_reservation_not_found(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("non-existent-id")


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Product A", None)
    service.adjust_stock("SKU001", 1000)

    for i in range(25):
        service.create_reservation("SKU001", 10, f"idempotency-{i}", 3600)

    result = service.list_orders(skip=0, limit=10)
    assert len(result["orders"]) == 0
    assert result["total"] == 0

    result = service.list_orders(skip=0, limit=5)
    assert result["skip"] == 0
    assert result["limit"] == 5
