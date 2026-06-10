import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import (
    InsufficientStockError,
    InvalidReservationStateError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repository):
    return Service(repository)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", "Test Product")
    assert sku.code == "SKU-001"
    assert sku.description == "Test Product"
    assert sku.id is not None


def test_create_sku_initializes_stock(service, repository):
    sku = service.create_sku("SKU-002", "Another Product")
    stock = repository.get_stock(sku.id)
    assert stock is not None
    assert stock.quantity == 0


def test_adjust_stock_success(service):
    sku = service.create_sku("SKU-003", "Product")
    stock = service.adjust_stock(sku.id, 100)
    assert stock.quantity == 100


def test_adjust_stock_negative_raises_error(service):
    sku = service.create_sku("SKU-004", "Product")
    with pytest.raises(InsufficientStockError):
        service.adjust_stock(sku.id, -10)


def test_adjust_stock_nonexistent_sku_raises_error(service):
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("nonexistent", 10)


def test_create_reservation_success(service):
    sku = service.create_sku("SKU-005", "Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 10)
    assert reservation.id is not None
    assert reservation.sku_id == sku.id
    assert reservation.quantity == 10
    assert reservation.status == "pending"


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("SKU-006", "Product")
    service.adjust_stock(sku.id, 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(sku.id, 10)


def test_create_reservation_idempotent(service):
    sku = service.create_sku("SKU-007", "Product")
    service.adjust_stock(sku.id, 100)

    res1 = service.create_reservation(sku.id, 10, idempotency_key="key-1")
    res2 = service.create_reservation(sku.id, 10, idempotency_key="key-1")

    assert res1.id == res2.id


def test_create_reservation_depletes_stock(service, repository):
    sku = service.create_sku("SKU-008", "Product")
    service.adjust_stock(sku.id, 50)

    service.create_reservation(sku.id, 20)
    stock = repository.get_stock(sku.id)
    assert stock.quantity == 30


def test_confirm_reservation_success(service):
    sku = service.create_sku("SKU-009", "Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 10)
    order = service.confirm_reservation(reservation.id)

    assert order.id is not None
    assert order.sku_id == sku.id
    assert order.quantity == 10
    assert order.status == "confirmed"


def test_confirm_reservation_nonexistent(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("nonexistent")


def test_confirm_reservation_expired(service, repository):
    sku = service.create_sku("SKU-010", "Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 10)
    expired_res = repository.get_reservation(reservation.id)
    expired_res.expires_at = datetime.utcnow() - timedelta(seconds=1)
    repository.session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_already_confirmed(service):
    sku = service.create_sku("SKU-011", "Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 10)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidReservationStateError):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    sku = service.create_sku("SKU-012", "Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 10)
    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == "cancelled"


def test_cancel_reservation_restores_stock(service, repository):
    sku = service.create_sku("SKU-013", "Product")
    service.adjust_stock(sku.id, 50)

    reservation = service.create_reservation(sku.id, 20)
    service.cancel_reservation(reservation.id)

    stock = repository.get_stock(sku.id)
    assert stock.quantity == 50


def test_cancel_reservation_nonexistent(service):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("nonexistent")


def test_cancel_confirmed_reservation_raises_error(service):
    sku = service.create_sku("SKU-014", "Product")
    service.adjust_stock(sku.id, 100)

    reservation = service.create_reservation(sku.id, 10)
    service.confirm_reservation(reservation.id)

    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation.id)


def test_list_orders(service):
    sku = service.create_sku("SKU-015", "Product")
    service.adjust_stock(sku.id, 300)

    for i in range(15):
        res = service.create_reservation(sku.id, 10)
        service.confirm_reservation(res.id)

    orders, total = service.list_orders(offset=0, limit=10)
    assert total == 15
    assert len(orders) == 10


def test_list_orders_pagination(service):
    sku = service.create_sku("SKU-016", "Product")
    service.adjust_stock(sku.id, 300)

    for i in range(25):
        res = service.create_reservation(sku.id, 10)
        service.confirm_reservation(res.id)

    page1, total = service.list_orders(offset=0, limit=10)
    page2, _ = service.list_orders(offset=10, limit=10)
    page3, _ = service.list_orders(offset=20, limit=10)

    assert total == 25
    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5
    assert page1[0].id != page2[0].id
