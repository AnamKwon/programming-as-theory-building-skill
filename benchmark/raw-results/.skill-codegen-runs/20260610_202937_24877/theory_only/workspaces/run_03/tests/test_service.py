import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from commerce_service.models import (
    init_db,
    get_session_factory,
    get_database_url,
    Base,
    SKUOrm,
    ReservationOrm,
)
from commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    database_url = "sqlite:///:memory:"
    SessionLocal = get_session_factory(database_url)
    Base.metadata.create_all(get_session_factory(database_url).__class__.kw["bind"])

    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)

    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(test_db: Session) -> CommerceService:
    return CommerceService(test_db)


def test_create_sku(service: CommerceService):
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku == "SKU-001"
    assert sku.initial_stock == 100
    assert sku.available_stock == 100


def test_adjust_stock(service: CommerceService):
    service.create_sku("SKU-002", 50)
    adjusted = service.adjust_stock("SKU-002", 20)
    assert adjusted.available_stock == 70

    adjusted = service.adjust_stock("SKU-002", -10)
    assert adjusted.available_stock == 60


def test_create_reservation_success(service: CommerceService):
    service.create_sku("SKU-003", 100)
    reservation = service.create_reservation("SKU-003", 30, "idempotency-key-1")

    assert reservation.sku == "SKU-003"
    assert reservation.quantity == 30
    assert reservation.status == "PENDING"

    sku = service.sku_repo.get_by_sku("SKU-003")
    assert sku.available_stock == 70


def test_create_reservation_insufficient_stock(service: CommerceService):
    service.create_sku("SKU-004", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-004", 100, "idempotency-key-2")


def test_create_reservation_idempotency(service: CommerceService):
    service.create_sku("SKU-005", 100)
    reservation1 = service.create_reservation("SKU-005", 25, "idempotency-key-3")

    sku_after_first = service.sku_repo.get_by_sku("SKU-005")
    stock_after_first = sku_after_first.available_stock

    reservation2 = service.create_reservation("SKU-005", 25, "idempotency-key-3")

    assert reservation1.id == reservation2.id
    assert stock_after_first == 75

    sku_after_second = service.sku_repo.get_by_sku("SKU-005")
    assert sku_after_second.available_stock == 75


def test_confirm_reservation_success(service: CommerceService):
    service.create_sku("SKU-006", 100)
    reservation = service.create_reservation("SKU-006", 20, "idempotency-key-4")
    order = service.confirm_reservation(reservation.id)

    assert order.reservation_id == reservation.id
    assert order.status == "CONFIRMED"

    updated_reservation = service.reservation_repo.get_by_id(reservation.id)
    assert updated_reservation.status == "CONFIRMED"


def test_confirm_reservation_not_pending(service: CommerceService):
    service.create_sku("SKU-007", 100)
    reservation = service.create_reservation("SKU-007", 20, "idempotency-key-5")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not pending"):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_expired(service: CommerceService, test_db: Session):
    service.create_sku("SKU-008", 100)
    reservation = service.create_reservation("SKU-008", 20, "idempotency-key-6")

    past_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = past_time
    test_db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)

    updated_reservation = service.reservation_repo.get_by_id(reservation.id)
    assert updated_reservation.status == "EXPIRED"

    sku = service.sku_repo.get_by_sku("SKU-008")
    assert sku.available_stock == 100


def test_cancel_reservation_success(service: CommerceService):
    service.create_sku("SKU-009", 100)
    reservation = service.create_reservation("SKU-009", 25, "idempotency-key-7")

    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == "CANCELLED"
    sku = service.sku_repo.get_by_sku("SKU-009")
    assert sku.available_stock == 100


def test_cancel_reservation_not_pending(service: CommerceService):
    service.create_sku("SKU-010", 100)
    reservation = service.create_reservation("SKU-010", 20, "idempotency-key-8")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not pending"):
        service.cancel_reservation(reservation.id)


def test_list_orders_pagination(service: CommerceService):
    service.create_sku("SKU-011", 1000)
    for i in range(25):
        reservation = service.create_reservation("SKU-011", 10, f"idempotency-key-{i}")
        service.confirm_reservation(reservation.id)

    orders, total = service.list_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 25

    orders, total = service.list_orders(page=2, size=10)
    assert len(orders) == 10

    orders, total = service.list_orders(page=3, size=10)
    assert len(orders) == 5
