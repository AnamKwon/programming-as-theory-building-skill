import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base, ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def service(db):
    repo = Repository(db)
    return Service(repo)


def test_create_sku(service):
    result = service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    assert result["code"] == "WIDGET-001"
    assert result["name"] == "Blue Widget"
    assert result["available_stock"] == 100


def test_adjust_stock(service):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=50)
    result = service.adjust_stock("WIDGET-001", 25)
    assert result["available_stock"] == 75


def test_create_reservation_success(service):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    result = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")
    assert result["sku_code"] == "WIDGET-001"
    assert result["quantity"] == 10
    assert result["state"] == ReservationState.PENDING.value


def test_create_reservation_insufficient_stock(service):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=5)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("WIDGET-001", 10, "idempotency-key-1")


def test_create_reservation_idempotent(service):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    res1 = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")
    res2 = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")
    assert res1["id"] == res2["id"]


def test_confirm_reservation(service, db):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    res = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")
    confirmed = service.confirm_reservation(res["id"])
    assert confirmed["state"] == ReservationState.CONFIRMED.value

    # Check stock was deducted
    repo = Repository(db)
    sku = repo.get_sku_by_code("WIDGET-001")
    assert sku.available_stock == 90


def test_confirm_expired_reservation(service, db):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    res = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")

    # Manually expire the reservation
    repo = Repository(db)
    reservation = repo.get_reservation_by_id(res["id"])
    reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(res["id"])


def test_cancel_pending_reservation(service):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    res = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")
    cancelled = service.cancel_reservation(res["id"])
    assert cancelled["state"] == ReservationState.CANCELLED.value


def test_cancel_confirmed_reservation(service, db):
    service.create_sku("WIDGET-001", "Blue Widget", initial_stock=100)
    res = service.create_reservation("WIDGET-001", 10, "idempotency-key-1")
    service.confirm_reservation(res["id"])

    # Check stock was deducted
    repo = Repository(db)
    sku = repo.get_sku_by_code("WIDGET-001")
    assert sku.available_stock == 90

    cancelled = service.cancel_reservation(res["id"])
    assert cancelled["state"] == ReservationState.CANCELLED.value

    # Check stock was refunded
    db.refresh(sku)
    assert sku.available_stock == 100


def test_create_order(service):
    order = service.create_order()
    assert order["state"] == "pending"
    assert order["reservation_ids"] == []


def test_list_orders_pagination(service):
    # Create 15 orders
    for _ in range(15):
        service.create_order()

    result = service.list_orders(page=1, page_size=10)
    assert result["total"] == 15
    assert len(result["items"]) == 10
    assert result["page"] == 1

    result = service.list_orders(page=2, page_size=10)
    assert len(result["items"]) == 5
    assert result["page"] == 2
