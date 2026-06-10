import pytest
from datetime import datetime, timedelta, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.repository import Base, Repository, ReservationStatus, OrderStatus
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    IdempotencyConflictError,
)

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    repo = Repository(db_session)
    return Service(repo), repo


def test_create_sku(service):
    svc, _ = service
    result = svc.create_sku("WIDGET-A", 100)
    assert result["name"] == "WIDGET-A"
    assert result["quantity"] == 100
    assert result["id"] == 1


def test_create_sku_duplicate_name_fails(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    with pytest.raises(ValueError, match="already exists"):
        svc.create_sku("WIDGET-A", 50)


def test_get_sku(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    result = svc.get_sku(1)
    assert result["name"] == "WIDGET-A"
    assert result["quantity"] == 100


def test_get_sku_not_found(service):
    svc, _ = service
    with pytest.raises(ValueError, match="not found"):
        svc.get_sku(999)


def test_adjust_stock_increases(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    result = svc.adjust_stock(1, 50)
    assert result["quantity"] == 150


def test_adjust_stock_decreases(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    result = svc.adjust_stock(1, -30)
    assert result["quantity"] == 70


def test_adjust_stock_clamps_to_zero(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    result = svc.adjust_stock(1, -200)
    assert result["quantity"] == 0


def test_adjust_stock_sku_not_found(service):
    svc, _ = service
    with pytest.raises(ValueError, match="not found"):
        svc.adjust_stock(999, 10)


def test_create_reservation_success(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    result = svc.create_reservation(1, 20, "idempotency-key-1")
    assert result["id"] == 1
    assert result["sku_id"] == 1
    assert result["quantity"] == 20
    assert result["status"] == "pending"
    assert result["idempotency_key"] == "idempotency-key-1"


def test_create_reservation_insufficient_stock(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    with pytest.raises(InsufficientStockError):
        svc.create_reservation(1, 200, "idempotency-key-1")


def test_create_reservation_sku_not_found(service):
    svc, _ = service
    with pytest.raises(ValueError, match="not found"):
        svc.create_reservation(999, 10, "idempotency-key-1")


def test_create_reservation_idempotent_retry_pending(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    result1 = svc.create_reservation(1, 20, "idempotency-key-1")
    result2 = svc.create_reservation(1, 20, "idempotency-key-1")
    assert result1["id"] == result2["id"]
    assert result2["status"] == "pending"


def test_create_reservation_idempotent_conflict_confirmed(service):
    svc, repo = service
    svc.create_sku("WIDGET-A", 100)
    res = svc.create_reservation(1, 20, "idempotency-key-1")
    repo.update_reservation_status(res["id"], ReservationStatus.CONFIRMED)
    with pytest.raises(IdempotencyConflictError):
        svc.create_reservation(1, 20, "idempotency-key-1")


def test_confirm_reservation(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    res = svc.create_reservation(1, 20, "idempotency-key-1")
    result = svc.confirm_reservation(res["id"])
    assert result["status"] == "confirmed"


def test_confirm_reservation_not_found(service):
    svc, _ = service
    with pytest.raises(ReservationNotFoundError):
        svc.confirm_reservation(999)


def test_confirm_reservation_invalid_state(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    res = svc.create_reservation(1, 20, "idempotency-key-1")
    svc.confirm_reservation(res["id"])
    with pytest.raises(InvalidStateTransitionError):
        svc.confirm_reservation(res["id"])


def test_confirm_reservation_expired(service, db_session):
    svc, repo = service
    svc.create_sku("WIDGET-A", 100)
    res = svc.create_reservation(1, 20, "idempotency-key-1")

    reservation = repo.get_reservation(res["id"])
    reservation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(ReservationExpiredError):
        svc.confirm_reservation(res["id"])


def test_cancel_reservation(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    res = svc.create_reservation(1, 20, "idempotency-key-1")
    result = svc.cancel_reservation(res["id"])
    assert result["status"] == "cancelled"


def test_cancel_reservation_not_found(service):
    svc, _ = service
    with pytest.raises(ReservationNotFoundError):
        svc.cancel_reservation(999)


def test_cancel_reservation_invalid_state(service):
    svc, _ = service
    svc.create_sku("WIDGET-A", 100)
    res = svc.create_reservation(1, 20, "idempotency-key-1")
    svc.cancel_reservation(res["id"])
    with pytest.raises(InvalidStateTransitionError):
        svc.cancel_reservation(res["id"])


def test_get_orders_empty(service):
    svc, _ = service
    result = svc.get_orders(offset=0, limit=10)
    assert result["total"] == 0
    assert result["orders"] == []
    assert result["offset"] == 0
    assert result["limit"] == 10


def test_get_orders_pagination(service):
    svc, repo = service
    svc.create_sku("WIDGET-A", 100)
    for i in range(5):
        res = svc.create_reservation(1, 10, f"key-{i}")
        repo.create_order([repo.get_reservation(res["id"])])

    result = svc.get_orders(offset=0, limit=2)
    assert result["total"] == 5
    assert len(result["orders"]) == 2
    assert result["offset"] == 0
    assert result["limit"] == 2

    result = svc.get_orders(offset=2, limit=2)
    assert len(result["orders"]) == 2
