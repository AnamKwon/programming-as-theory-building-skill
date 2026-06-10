import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service import models
from src.commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(test_db):
    return CommerceService(test_db)


def test_create_sku(service):
    sku = service.create_sku("SKU001", "Test Product", 99.99)
    assert sku.id == "SKU001"
    assert sku.name == "Test Product"
    assert sku.price == 99.99


def test_create_duplicate_sku_fails(service):
    service.create_sku("SKU001", "Product 1", 50.0)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("SKU001", "Product 2", 75.0)


def test_adjust_stock_nonexistent_sku_fails(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_adjust_stock_success(service):
    service.create_sku("SKU001", "Product", 100.0)
    stock = service.adjust_stock("SKU001", 50)
    assert stock.quantity == 50

    stock = service.adjust_stock("SKU001", 30)
    assert stock.quantity == 80


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 5)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 10, "idempotent-key-1")


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    reservation = service.create_reservation("SKU001", 30, "idempotent-key-1")
    assert reservation.sku_id == "SKU001"
    assert reservation.quantity == 30
    assert reservation.status == models.ReservationStatus.PENDING

    stock = service.stock.get("SKU001")
    assert stock.quantity == 20


def test_idempotent_reservation_retry(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    res1 = service.create_reservation("SKU001", 30, "idempotent-key-1")
    res2 = service.create_reservation("SKU001", 30, "idempotent-key-1")

    assert res1.id == res2.id
    stock = service.stock.get("SKU001")
    assert stock.quantity == 20


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    reservation = service.create_reservation("SKU001", 30, "idempotent-key-1")
    confirmed = service.confirm_reservation(reservation.id)

    assert confirmed.status == models.ReservationStatus.CONFIRMED
    order = service.orders.get(confirmed.order_id)
    assert order.status == models.OrderStatus.CONFIRMED


def test_confirm_reservation_expired(service, test_db):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    reservation = service.create_reservation("SKU001", 30, "idempotent-key-1")

    expired_time = datetime.utcnow() - timedelta(minutes=5)
    test_db.query(models.Reservation).filter(
        models.Reservation.id == reservation.id
    ).update({"expires_at": expired_time})
    test_db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)


def test_cancel_pending_reservation(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    reservation = service.create_reservation("SKU001", 30, "idempotent-key-1")
    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == models.ReservationStatus.CANCELLED
    stock = service.stock.get("SKU001")
    assert stock.quantity == 50


def test_cancel_confirmed_reservation_fails(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    reservation = service.create_reservation("SKU001", 30, "idempotent-key-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="Cannot cancel confirmed"):
        service.cancel_reservation(reservation.id)


def test_get_order(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 50)

    reservation = service.create_reservation("SKU001", 30, "idempotent-key-1")
    order = service.get_order(reservation.order_id)

    assert order.status == models.OrderStatus.RESERVED


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Product", 100.0)
    service.adjust_stock("SKU001", 1000)

    for i in range(25):
        service.create_reservation("SKU001", 10, f"key-{i}")

    orders, total = service.list_orders(limit=10, offset=0)
    assert len(orders) == 10
    assert total == 25

    orders, total = service.list_orders(limit=10, offset=10)
    assert len(orders) == 10

    orders, total = service.list_orders(limit=10, offset=20)
    assert len(orders) == 5
