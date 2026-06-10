import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


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
    return Repository(db)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service, repo):
    sku = service.create_sku("SKU001", 100)
    assert sku.sku == "SKU001"
    assert sku.stock == 100

    fetched = repo.get_sku_by_name("SKU001")
    assert fetched.stock == 100


def test_create_sku_duplicate_fails(service):
    service.create_sku("SKU001", 100)
    with pytest.raises(Exception):
        service.create_sku("SKU001", 50)


def test_adjust_stock(service, repo):
    service.create_sku("SKU001", 100)
    adjusted = service.adjust_stock("SKU001", 10)
    assert adjusted.stock == 110

    adjusted = service.adjust_stock("SKU001", -20)
    assert adjusted.stock == 90


def test_adjust_stock_nonexistent_fails(service):
    with pytest.raises(Exception):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_happy_path(service, repo):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-1")
    assert reservation.sku == "SKU001"
    assert reservation.quantity == 50
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-1"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 50)
    with pytest.raises(Exception) as exc_info:
        service.create_reservation("SKU001", 100, "idempotency-1")
    assert "Insufficient stock" in str(exc_info.value)


def test_create_reservation_idempotency(service, repo):
    service.create_sku("SKU001", 100)
    res1 = service.create_reservation("SKU001", 50, "idempotency-1")
    res2 = service.create_reservation("SKU001", 50, "idempotency-1")

    assert res1.id == res2.id
    assert res1.quantity == res2.quantity
    fetched_sku = repo.get_sku_by_name("SKU001")
    assert fetched_sku.stock == 100


def test_create_reservation_respects_pending_stock(service):
    service.create_sku("SKU001", 100)
    service.create_reservation("SKU001", 50, "idempotency-1")

    with pytest.raises(Exception) as exc_info:
        service.create_reservation("SKU001", 60, "idempotency-2")
    assert "Insufficient stock" in str(exc_info.value)

    res3 = service.create_reservation("SKU001", 50, "idempotency-3")
    assert res3.status == "PENDING"


def test_confirm_reservation_happy_path(service, repo):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-1")

    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == "CONFIRMED"

    fetched = repo.get_reservation_by_id(reservation.id)
    assert fetched.status == "CONFIRMED"

    order = repo.session.query(repo.session.query.from_statement("SELECT * FROM orders")).all()


def test_confirm_reservation_not_pending_fails(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation.id)
    assert "not in PENDING state" in str(exc_info.value)


def test_cancel_reservation_restores_stock(service, repo):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-1")

    sku_before = repo.get_sku_by_name("SKU001")
    available_before = repo.get_available_stock("SKU001")

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "CANCELLED"

    available_after = repo.get_available_stock("SKU001")
    assert available_after == 100


def test_cancel_reservation_not_pending_fails(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(Exception) as exc_info:
        service.cancel_reservation(reservation.id)
    assert "not in PENDING state" in str(exc_info.value)


def test_confirm_expired_reservation_fails(service, repo):
    import time

    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 50, "idempotency-1")

    old_time = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 400, tz=timezone.utc
    )
    db_res = repo.get_reservation_by_id(reservation.id)
    db_res.created_at = old_time
    repo.session.commit()

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(reservation.id)
    assert "expired" in str(exc_info.value)

    updated_res = repo.get_reservation_by_id(reservation.id)
    assert updated_res.status == "EXPIRED"

    available = repo.get_available_stock("SKU001")
    assert available == 100


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)
    for i in range(25):
        res = service.create_reservation("SKU001", 10, f"idempotency-{i}")
        service.confirm_reservation(res.id)

    page1 = service.get_orders(page=1, size=10)
    assert len(page1.orders) == 10
    assert page1.page == 1
    assert page1.size == 10
    assert page1.total == 25

    page2 = service.get_orders(page=2, size=10)
    assert len(page2.orders) == 10

    page3 = service.get_orders(page=3, size=10)
    assert len(page3.orders) == 5
