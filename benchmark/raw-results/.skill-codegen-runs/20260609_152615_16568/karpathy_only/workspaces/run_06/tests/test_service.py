import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service import models
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    ReservationNotFoundError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    return Service(Repository(db))


def test_create_sku(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    assert sku.sku_code == "SKU-001"
    assert sku.name == "Widget"
    assert sku.stock_quantity == 100


def test_adjust_stock(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    adjusted = service.adjust_stock(sku.id, 10)
    assert adjusted.stock_quantity == 110

    adjusted = service.adjust_stock(sku.id, -30)
    assert adjusted.stock_quantity == 80


def test_create_reservation_sufficient_stock(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    reservation = service.create_reservation("req-1", [(sku.id, 50)], 30)
    assert reservation.status == models.ReservationStatus.PENDING
    assert reservation.idempotency_key == "req-1"
    assert sku.stock_quantity == 50  # Stock should be reduced


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    with pytest.raises(InsufficientStockError):
        service.create_reservation("req-1", [(sku.id, 150)], 30)


def test_create_reservation_idempotent_retry(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    res1 = service.create_reservation("req-1", [(sku.id, 50)], 30)
    res2 = service.create_reservation("req-1", [(sku.id, 50)], 30)

    assert res1.id == res2.id
    # Stock should only be reserved once
    sku_after = service.adjust_stock(sku.id, 0)
    assert sku_after.stock_quantity == 50


def test_confirm_reservation(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    reservation = service.create_reservation("req-1", [(sku.id, 50)], 30)

    order = service.confirm_reservation(reservation.reservation_id)
    assert order.status == models.OrderStatus.CONFIRMED
    assert order.order_id.startswith("ord-")


def test_cancel_reservation_releases_stock(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    reservation = service.create_reservation("req-1", [(sku.id, 50)], 30)

    service.cancel_reservation(reservation.reservation_id)

    # Stock should be released
    updated_sku = service.adjust_stock(sku.id, 0)
    assert updated_sku.stock_quantity == 100


def test_confirm_expired_reservation(service, db):
    sku = service.create_sku("SKU-001", "Widget", 100)
    reservation = service.create_reservation("req-1", [(sku.id, 50)], 30)

    # Manually expire the reservation
    reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.reservation_id)


def test_cannot_confirm_non_pending_reservation(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    reservation = service.create_reservation("req-1", [(sku.id, 50)], 30)
    order1 = service.confirm_reservation(reservation.reservation_id)

    # Attempt to confirm again
    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(reservation.reservation_id)


def test_get_order(service):
    sku = service.create_sku("SKU-001", "Widget", 100)
    reservation = service.create_reservation("req-1", [(sku.id, 50)], 30)
    order = service.confirm_reservation(reservation.reservation_id)

    retrieved = service.get_order(order.order_id)
    assert retrieved.order_id == order.order_id
    assert retrieved.status == models.OrderStatus.CONFIRMED


def test_list_orders_pagination(service):
    sku = service.create_sku("SKU-001", "Widget", 100)

    # Create multiple orders
    for i in range(15):
        reservation = service.create_reservation(f"req-{i}", [(sku.id, 1)], 30)
        service.confirm_reservation(reservation.reservation_id)

    orders1, total1 = service.list_orders(skip=0, limit=10)
    assert len(orders1) == 10
    assert total1 == 15

    orders2, total2 = service.list_orders(skip=10, limit=10)
    assert len(orders2) == 5
    assert total2 == 15
