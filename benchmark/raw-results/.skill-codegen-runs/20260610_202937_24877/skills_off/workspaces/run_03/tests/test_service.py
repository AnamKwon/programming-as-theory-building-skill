import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.repository import Base, SKU, Reservation, Order, SKURepository, ReservationRepository, OrderRepository
from src.commerce_service.service import CommerceService
from src.commerce_service.models import SKUCreate, ReservationCreate


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    sku_create = SKUCreate(sku="SKU001", initial_stock=100)
    sku = service.create_sku(sku_create)

    assert sku.sku == "SKU001"
    assert sku.available_stock == 100
    assert sku.id is not None


def test_adjust_stock(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    adjusted = service.adjust_stock("SKU001", -10)
    assert adjusted.available_stock == 90

    adjusted = service.adjust_stock("SKU001", 20)
    assert adjusted.available_stock == 110


def test_create_reservation_sufficient_stock(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    assert reservation is not None
    assert reservation.sku == "SKU001"
    assert reservation.quantity == 30
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "key123"

    sku = service.sku_repo.get_by_sku("SKU001")
    assert sku.available_stock == 70


def test_create_reservation_insufficient_stock(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=20))

    res_create = ReservationCreate(sku="SKU001", quantity=50, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    assert reservation is None

    sku = service.sku_repo.get_by_sku("SKU001")
    assert sku.available_stock == 20


def test_reservation_idempotency(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    res1 = service.create_reservation(res_create)

    sku_after_first = service.sku_repo.get_by_sku("SKU001")
    stock_after_first = sku_after_first.available_stock

    res2 = service.create_reservation(res_create)

    assert res1.id == res2.id
    assert res1.idempotency_key == res2.idempotency_key

    sku_after_second = service.sku_repo.get_by_sku("SKU001")
    stock_after_second = sku_after_second.available_stock

    assert stock_after_first == stock_after_second


def test_confirm_reservation_success(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    confirmed, status = service.confirm_reservation(reservation.id)

    assert status == "success"
    assert confirmed.status == "CONFIRMED"

    order_repo = OrderRepository(db)
    orders, _ = order_repo.get_all(1, 10)
    assert len(orders) == 1
    assert orders[0].reservation_id == reservation.id


def test_confirm_reservation_not_pending(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    service.confirm_reservation(reservation.id)

    confirmed, status = service.confirm_reservation(reservation.id)

    assert status == "invalid_state"
    assert confirmed is None


def test_confirm_reservation_expired(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    db_reservation = service.reservation_repo.get_by_id(reservation.id)
    db_reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
    db.commit()

    confirmed, status = service.confirm_reservation(reservation.id)

    assert status == "expired"
    assert confirmed is None

    expired_reservation = service.reservation_repo.get_by_id(reservation.id)
    assert expired_reservation.status == "EXPIRED"

    sku = service.sku_repo.get_by_sku("SKU001")
    assert sku.available_stock == 100


def test_cancel_reservation(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    sku_before = service.sku_repo.get_by_sku("SKU001")
    assert sku_before.available_stock == 70

    cancelled, status = service.cancel_reservation(reservation.id)

    assert status == "success"
    assert cancelled.status == "CANCELLED"

    sku_after = service.sku_repo.get_by_sku("SKU001")
    assert sku_after.available_stock == 100


def test_cancel_reservation_not_pending(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    res_create = ReservationCreate(sku="SKU001", quantity=30, idempotency_key="key123")
    reservation = service.create_reservation(res_create)

    service.confirm_reservation(reservation.id)

    cancelled, status = service.cancel_reservation(reservation.id)

    assert status == "invalid_state"
    assert cancelled is None


def test_get_orders_pagination(service, db):
    service.create_sku(SKUCreate(sku="SKU001", initial_stock=100))

    for i in range(25):
        res_create = ReservationCreate(sku="SKU001", quantity=1, idempotency_key=f"key{i}")
        reservation = service.create_reservation(res_create)
        service.confirm_reservation(reservation.id)

    result = service.get_orders(page=1, size=10)
    assert len(result.items) == 10
    assert result.page == 1
    assert result.size == 10
    assert result.total == 25

    result = service.get_orders(page=2, size=10)
    assert len(result.items) == 10

    result = service.get_orders(page=3, size=10)
    assert len(result.items) == 5
