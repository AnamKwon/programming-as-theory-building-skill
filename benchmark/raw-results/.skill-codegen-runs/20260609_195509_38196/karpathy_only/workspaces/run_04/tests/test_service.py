import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.repository import Base, Repository
from commerce_service.service import CommerceService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(db_session):
    return CommerceService(db_session)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["id"] is not None
    assert result["sku_name"] == "SKU-001"
    assert result["available_stock"] == 100
    assert result["reserved_stock"] == 0


def test_create_duplicate_sku(service):
    service.create_sku("SKU-001", 100)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("SKU-001", 50)


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock(1, 50)
    assert result["available_stock"] == 150

    result = service.adjust_stock(1, -30)
    assert result["available_stock"] == 120


def test_adjust_stock_nonexistent(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock(999, 10)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")
    assert result["id"] is not None
    assert result["quantity"] == 50
    assert result["status"] == "pending"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation(1, 50, "idempotency-key-1")


def test_create_reservation_idempotent(service):
    service.create_sku("SKU-001", 100)
    result1 = service.create_reservation(1, 50, "idempotency-key-1")
    result2 = service.create_reservation(1, 50, "idempotency-key-1")
    assert result1["id"] == result2["id"]


def test_create_reservation_after_cancel_fails(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")
    service.cancel_reservation(result["id"])
    with pytest.raises(ValueError, match="was cancelled"):
        service.create_reservation(1, 50, "idempotency-key-1")


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    reservation = service.create_reservation(1, 50, "idempotency-key-1")
    result = service.confirm_reservation(reservation["id"])
    assert result["order_id"] is not None
    assert result["status"] == "confirmed"


def test_confirm_expired_reservation(service, db_session):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")

    repo = Repository(db_session)
    reservation = repo.get_reservation(result["id"])
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(ValueError, match="has expired"):
        service.confirm_reservation(result["id"])


def test_confirm_nonpending_reservation(service, db_session):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")
    service.confirm_reservation(result["id"])

    with pytest.raises(ValueError, match="not pending"):
        service.confirm_reservation(result["id"])


def test_cancel_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")
    cancel_result = service.cancel_reservation(result["id"])
    assert cancel_result["status"] == "cancelled"


def test_cancel_confirmed_reservation(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation(1, 50, "idempotency-key-1")
    service.confirm_reservation(result["id"])
    with pytest.raises(ValueError, match="Cannot cancel a confirmed"):
        service.cancel_reservation(result["id"])


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 100)

    for i in range(25):
        result = service.create_reservation(1, 10, f"idempotency-key-{i}")
        service.confirm_reservation(result["id"])

    page1 = service.get_orders(limit=10, offset=0)
    assert len(page1["orders"]) == 10
    assert page1["total"] == 25
    assert page1["limit"] == 10
    assert page1["offset"] == 0

    page2 = service.get_orders(limit=10, offset=10)
    assert len(page2["orders"]) == 10

    page3 = service.get_orders(limit=10, offset=20)
    assert len(page3["orders"]) == 5
