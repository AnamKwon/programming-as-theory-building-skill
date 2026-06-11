import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from commerce_service.repository import Base, Repository
from commerce_service.service import CommerceService

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_service_commerce.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def repository(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    sku = service.create_sku("TEST-001", 100)
    assert sku.sku == "TEST-001"
    assert sku.stock == 100


def test_create_duplicate_sku(service):
    service.create_sku("TEST-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_sku("TEST-001", 50)
    assert exc_info.value.status_code == 400


def test_adjust_stock(service):
    service.create_sku("TEST-001", 100)
    sku = service.adjust_stock("TEST-001", 50)
    assert sku.stock == 150


def test_adjust_stock_nonexistent(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 50)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service):
    service.create_sku("TEST-001", 100)
    reservation = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    assert reservation.sku == "TEST-001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-key-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("TEST-001", 30)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("TEST-001", 50, "idempotency-key-1")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Insufficient stock"


def test_create_reservation_idempotency(service):
    service.create_sku("TEST-001", 100)
    res1 = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    res2 = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    assert res1.id == res2.id


def test_create_reservation_deducts_stock(service, repository):
    service.create_sku("TEST-001", 100)
    service.create_reservation("TEST-001", 50, "idempotency-key-1")
    sku = repository.get_sku("TEST-001")
    assert sku.stock == 50


def test_confirm_reservation_success(service):
    service.create_sku("TEST-001", 100)
    reservation = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    order = service.confirm_reservation(reservation.id)
    assert order.reservation_id == reservation.id
    assert order.sku == "TEST-001"
    assert order.quantity == 50


def test_confirm_reservation_nonexistent(service):
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_confirm_reservation_not_pending(service):
    service.create_sku("TEST-001", 100)
    reservation = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    service.confirm_reservation(reservation.id)
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Reservation is not in PENDING status"


def test_confirm_reservation_expired(service, repository):
    service.create_sku("TEST-001", 100)
    reservation = service.create_reservation("TEST-001", 50, "idempotency-key-1")

    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    db_reservation = repository.get_reservation(reservation.id)
    db_reservation.created_at = old_time
    repository.db.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Reservation expired"

    updated_reservation = repository.get_reservation(reservation.id)
    assert updated_reservation.status == "EXPIRED"

    sku = repository.get_sku("TEST-001")
    assert sku.stock == 100


def test_cancel_reservation_success(service, repository):
    service.create_sku("TEST-001", 100)
    reservation = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    service.cancel_reservation(reservation.id)

    updated_reservation = repository.get_reservation(reservation.id)
    assert updated_reservation.status == "CANCELLED"

    sku = repository.get_sku("TEST-001")
    assert sku.stock == 100


def test_cancel_reservation_nonexistent(service):
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404


def test_cancel_reservation_not_pending(service):
    service.create_sku("TEST-001", 100)
    reservation = service.create_reservation("TEST-001", 50, "idempotency-key-1")
    service.confirm_reservation(reservation.id)
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation.id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Reservation is not in PENDING status"


def test_get_orders_pagination(service):
    service.create_sku("TEST-001", 1000)

    for i in range(25):
        reservation = service.create_reservation("TEST-001", 10, f"idempotency-key-{i}")
        service.confirm_reservation(reservation.id)

    orders, total = service.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 25

    orders, total = service.get_orders(page=2, size=10)
    assert len(orders) == 10
    assert total == 25

    orders, total = service.get_orders(page=3, size=10)
    assert len(orders) == 5
    assert total == 25


def test_multiple_reservations_same_sku(service, repository):
    service.create_sku("TEST-001", 100)

    res1 = service.create_reservation("TEST-001", 30, "key-1")
    assert res1.status == "PENDING"

    res2 = service.create_reservation("TEST-001", 20, "key-2")
    assert res2.status == "PENDING"

    sku = repository.get_sku("TEST-001")
    assert sku.stock == 50
