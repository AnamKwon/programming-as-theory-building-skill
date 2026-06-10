import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.service import CommerceService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    return CommerceService(db_session)


def test_create_sku(service):
    sku = service.create_sku(code="TEST001", name="Test Product", initial_stock=100)
    assert sku.id is not None
    assert sku.code == "TEST001"
    assert sku.name == "Test Product"
    assert sku.available_stock == 100
    assert sku.reserved_stock == 0


def test_get_sku(service):
    created = service.create_sku(code="TEST002", name="Test Product", initial_stock=50)
    sku = service.get_sku(created.id)
    assert sku is not None
    assert sku.code == "TEST002"


def test_get_sku_not_found(service):
    sku = service.get_sku(9999)
    assert sku is None


def test_adjust_stock_increase(service):
    sku = service.create_sku(code="TEST003", name="Test", initial_stock=50)
    adjusted = service.adjust_stock(sku.id, 30)
    assert adjusted.available_stock == 80


def test_adjust_stock_decrease(service):
    sku = service.create_sku(code="TEST004", name="Test", initial_stock=50)
    adjusted = service.adjust_stock(sku.id, -20)
    assert adjusted.available_stock == 30


def test_adjust_stock_insufficient(service):
    sku = service.create_sku(code="TEST005", name="Test", initial_stock=50)
    with pytest.raises(ValueError, match="Insufficient available stock"):
        service.adjust_stock(sku.id, -100)


def test_create_reservation_success(service):
    sku = service.create_sku(code="TEST006", name="Test", initial_stock=100)
    reservation = service.create_reservation(
        sku_id=sku.id, quantity=25, idempotency_key="key1", ttl_seconds=3600
    )
    assert reservation.id is not None
    assert reservation.status == "pending"
    assert reservation.quantity == 25

    updated_sku = service.get_sku(sku.id)
    assert updated_sku.available_stock == 75
    assert updated_sku.reserved_stock == 25


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku(code="TEST007", name="Test", initial_stock=50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation(
            sku_id=sku.id, quantity=100, idempotency_key="key2", ttl_seconds=3600
        )


def test_create_reservation_idempotency(service):
    sku = service.create_sku(code="TEST008", name="Test", initial_stock=100)
    key = "idempotent-key"

    res1 = service.create_reservation(sku_id=sku.id, quantity=30, idempotency_key=key, ttl_seconds=3600)
    res2 = service.create_reservation(sku_id=sku.id, quantity=30, idempotency_key=key, ttl_seconds=3600)

    assert res1.id == res2.id
    assert service.get_sku(sku.id).reserved_stock == 30


def test_confirm_reservation(service):
    sku = service.create_sku(code="TEST009", name="Test", initial_stock=100)
    reservation = service.create_reservation(
        sku_id=sku.id, quantity=40, idempotency_key="key3", ttl_seconds=3600
    )

    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == "confirmed"

    updated_sku = service.get_sku(sku.id)
    assert updated_sku.available_stock == 60
    assert updated_sku.reserved_stock == 0


def test_cancel_reservation(service):
    sku = service.create_sku(code="TEST010", name="Test", initial_stock=100)
    reservation = service.create_reservation(
        sku_id=sku.id, quantity=35, idempotency_key="key4", ttl_seconds=3600
    )

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "cancelled"

    updated_sku = service.get_sku(sku.id)
    assert updated_sku.available_stock == 100
    assert updated_sku.reserved_stock == 0


def test_cancel_confirmed_reservation_fails(service):
    sku = service.create_sku(code="TEST011", name="Test", initial_stock=100)
    reservation = service.create_reservation(
        sku_id=sku.id, quantity=50, idempotency_key="key5", ttl_seconds=3600
    )
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="Cannot cancel a confirmed reservation"):
        service.cancel_reservation(reservation.id)


def test_confirm_non_pending_reservation(service):
    sku = service.create_sku(code="TEST012", name="Test", initial_stock=100)
    reservation = service.create_reservation(
        sku_id=sku.id, quantity=25, idempotency_key="key6", ttl_seconds=3600
    )
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="Cannot confirm reservation in status"):
        service.confirm_reservation(reservation.id)
