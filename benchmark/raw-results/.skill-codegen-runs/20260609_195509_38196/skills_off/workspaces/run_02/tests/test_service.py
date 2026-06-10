import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    SKUNotFoundError,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=None
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def service(db):
    return CommerceService(Repository(db))


def test_create_sku(service):
    result = service.create_sku("SKU001")
    assert result["code"] == "SKU001"
    assert "id" in result


def test_adjust_stock_positive(service):
    service.create_sku("SKU001")
    result = service.adjust_stock("SKU001", 100)
    assert result["quantity"] == 100
    assert result["sku_code"] == "SKU001"


def test_adjust_stock_negative(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)
    result = service.adjust_stock("SKU001", -30)
    assert result["quantity"] == 70


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1")
    assert result["id"]
    assert result["quantity"] == 10
    assert result["status"] == "pending"
    assert "expires_at" in result


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 5)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 10, "idempotency-1")


def test_create_reservation_idempotent(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)
    result1 = service.create_reservation("SKU001", 10, "idempotency-1")
    result2 = service.create_reservation("SKU001", 10, "idempotency-1")
    assert result1["id"] == result2["id"]


def test_create_reservation_blocks_other_stock(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 15)
    service.create_reservation("SKU001", 10, "idempotency-1")
    with pytest.raises(InsufficientStockError):
        service.create_reservation("SKU001", 10, "idempotency-2")


def test_confirm_reservation(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-1")
    order = service.confirm_reservation(res["id"])
    assert order["order_id"]
    assert order["quantity"] == 10
    assert order["status"] == "pending"


def test_confirm_expired_reservation(service):
    repo = service.repo
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)

    # Create reservation with past expiry
    sku = repo.get_sku_by_code("SKU001")
    expired_at = datetime.utcnow() - timedelta(seconds=10)
    reservation = repo.create_reservation("idempotency-1", sku.id, 10, expired_at)
    repo.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-1")
    result = service.cancel_reservation(res["id"])
    assert result["status"] == "cancelled"


def test_get_order(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-1")
    order = service.confirm_reservation(res["id"])
    retrieved = service.get_order(order["order_id"])
    assert retrieved["id"] == order["order_id"]
    assert retrieved["quantity"] == 10


def test_list_orders_pagination(service):
    service.create_sku("SKU001")
    service.adjust_stock("SKU001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU001", 10, f"idempotency-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.list_orders(limit=10, offset=0)
    assert len(page1["orders"]) == 10
    assert page1["total"] == 25
    assert page1["limit"] == 10
    assert page1["offset"] == 0

    page2 = service.list_orders(limit=10, offset=10)
    assert len(page2["orders"]) == 10
    assert page2["offset"] == 10

    page3 = service.list_orders(limit=10, offset=20)
    assert len(page3["orders"]) == 5
