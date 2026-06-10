import pytest
import time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.service import CommerceService
from src.commerce_service.repository import Repository

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_service.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def test_create_sku(db_session):
    service = CommerceService(db_session)
    sku = service.create_sku("SKU001", 100)
    assert sku.sku == "SKU001"
    assert sku.available_stock == 100


def test_adjust_stock(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)
    updated = service.adjust_stock("SKU001", 50)
    assert updated.available_stock == 150


def test_create_reservation_success(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)
    response, status = service.create_reservation("SKU001", 30, "key-1")
    assert status == 201
    assert response["quantity"] == 30
    assert response["status"] == "PENDING"


def test_create_reservation_insufficient_stock(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 50)
    response, status = service.create_reservation("SKU001", 100, "key-1")
    assert status == 400
    assert response["detail"] == "Insufficient stock"


def test_create_reservation_idempotency(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)

    response1, status1 = service.create_reservation("SKU001", 30, "key-1")
    res_id_1 = response1["id"]

    response2, status2 = service.create_reservation("SKU001", 30, "key-1")
    res_id_2 = response2["id"]

    assert res_id_1 == res_id_2
    assert status2 == 201


def test_create_reservation_stock_deduction(db_session):
    repo = Repository(db_session)
    service = CommerceService(db_session)

    service.create_sku("SKU001", 100)
    service.create_reservation("SKU001", 30, "key-1")

    sku = repo.get_sku_by_sku_code("SKU001")
    assert sku.available_stock == 70


def test_confirm_reservation_success(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)
    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    order_response, status = service.confirm_reservation(res_id)
    assert status == 200
    assert "id" in order_response


def test_confirm_reservation_expired(db_session):
    service = CommerceService(db_session)
    repo = Repository(db_session)

    service.create_sku("SKU001", 100)
    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    time.sleep(301)

    response, status = service.confirm_reservation(res_id)
    assert status == 400
    assert response["detail"] == "Reservation expired"

    reservation = repo.get_reservation_by_id(res_id)
    assert reservation.status == ReservationStatus.EXPIRED

    sku = repo.get_sku_by_sku_code("SKU001")
    assert sku.available_stock == 100


def test_confirm_non_pending_reservation(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)
    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    response, status = service.confirm_reservation(res_id)
    assert status == 400


def test_cancel_reservation_success(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)
    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    response, status = service.cancel_reservation(res_id)
    assert status == 200
    assert response["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(db_session):
    repo = Repository(db_session)
    service = CommerceService(db_session)

    service.create_sku("SKU001", 100)
    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    service.cancel_reservation(res_id)

    sku = repo.get_sku_by_sku_code("SKU001")
    assert sku.available_stock == 100


def test_cancel_non_pending_reservation(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 100)
    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    response, status = service.cancel_reservation(res_id)
    assert status == 400


def test_get_orders_pagination(db_session):
    service = CommerceService(db_session)
    service.create_sku("SKU001", 500)

    for i in range(15):
        res, _ = service.create_reservation("SKU001", 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    response, status = service.get_orders(page=1, size=10)
    assert status == 200
    assert len(response["items"]) == 10
    assert response["total"] == 15
    assert response["pages"] == 2

    response, status = service.get_orders(page=2, size=10)
    assert len(response["items"]) == 5


def test_happy_path(db_session):
    service = CommerceService(db_session)
    repo = Repository(db_session)

    service.create_sku("SKU001", 100)

    res, _ = service.create_reservation("SKU001", 30, "key-1")
    res_id = res["id"]

    order_response, _ = service.confirm_reservation(res_id)
    order_id = order_response["id"]

    orders, _ = service.get_orders(page=1, size=10)
    assert orders["total"] == 1
    assert orders["items"][0]["id"] == order_id
