import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import (
    OrderService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repo(db):
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return OrderService(repo)


def test_create_sku(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    assert sku.code == "SKU001"
    assert sku.name == "Product A"
    session.close()


def test_create_sku_duplicate(service):
    session = service.repo.get_session()
    sku1 = service.create_sku(session, "SKU001", "Product A")
    sku2 = service.create_sku(session, "SKU001", "Product A")
    assert sku1.id == sku2.id
    session.close()


def test_adjust_stock(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    stock = service.adjust_stock(session, sku.id, 100)
    assert stock.quantity == 100
    assert stock.reserved == 0
    session.close()


def test_adjust_stock_negative(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    stock = service.adjust_stock(session, sku.id, -30)
    assert stock.quantity == 70
    session.close()


def test_create_reservation_happy_path(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(
        session, sku.id, 50, "idempotency-1"
    )
    assert reservation.quantity == 50
    assert not reservation.is_confirmed()
    stock = service.get_stock(session, sku.id)
    assert stock.reserved == 50
    session.close()


def test_create_reservation_insufficient_stock(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 30)
    with pytest.raises(InsufficientStockError):
        service.create_reservation(session, sku.id, 50, "idempotency-1")
    session.close()


def test_create_reservation_idempotent(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    res1 = service.create_reservation(session, sku.id, 50, "idempotency-1")
    res2 = service.create_reservation(session, sku.id, 50, "idempotency-1")
    assert res1.id == res2.id
    stock = service.get_stock(session, sku.id)
    assert stock.reserved == 50
    session.close()


def test_create_reservation_expired_retry(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)

    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")
    reservation.expires_at = datetime.utcnow() - timedelta(hours=1)
    session.commit()

    with pytest.raises(ReservationExpiredError):
        service.create_reservation(session, sku.id, 50, "idempotency-1")
    session.close()


def test_confirm_reservation_happy_path(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")

    order = service.confirm_reservation(session, reservation.id)
    assert order.status == "PENDING"
    assert order.reservation_id == reservation.id

    updated_reservation = service.repo.get_reservation_by_id(session, reservation.id)
    assert updated_reservation.is_confirmed()
    session.close()


def test_confirm_reservation_idempotent(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")

    order1 = service.confirm_reservation(session, reservation.id)
    order2 = service.confirm_reservation(session, reservation.id)
    assert order1.id == order2.id
    session.close()


def test_confirm_reservation_expired(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")

    reservation.expires_at = datetime.utcnow() - timedelta(hours=1)
    session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(session, reservation.id)

    stock = service.get_stock(session, sku.id)
    assert stock.reserved == 0
    session.close()


def test_cancel_reservation_happy_path(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")

    service.cancel_reservation(session, reservation.id)

    stock = service.get_stock(session, sku.id)
    assert stock.reserved == 0

    retrieved = service.repo.get_reservation_by_id(session, reservation.id)
    assert retrieved is None
    session.close()


def test_cancel_reservation_confirmed(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")

    order = service.confirm_reservation(session, reservation.id)
    service.cancel_reservation(session, reservation.id)

    updated_order = service.repo.get_order_by_id(session, order.id)
    assert updated_order.status == "CANCELLED"
    session.close()


def test_cancel_reservation_not_found(service):
    session = service.repo.get_session()
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(session, "nonexistent")
    session.close()


def test_get_order(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 100)
    reservation = service.create_reservation(session, sku.id, 50, "idempotency-1")
    order = service.confirm_reservation(session, reservation.id)

    retrieved = service.get_order(session, order.id)
    assert retrieved.id == order.id
    assert retrieved.status == "PENDING"
    session.close()


def test_list_orders_pagination(service):
    session = service.repo.get_session()
    sku = service.create_sku(session, "SKU001", "Product A")
    service.adjust_stock(session, sku.id, 1000)

    for i in range(5):
        res = service.create_reservation(session, sku.id, 10, f"idempotency-{i}")
        service.confirm_reservation(session, res.id)

    orders, total = service.list_orders(session, limit=2, offset=0)
    assert len(orders) == 2
    assert total == 5

    orders, total = service.list_orders(session, limit=2, offset=2)
    assert len(orders) == 2

    orders, total = service.list_orders(session, limit=2, offset=4)
    assert len(orders) == 1
    session.close()
