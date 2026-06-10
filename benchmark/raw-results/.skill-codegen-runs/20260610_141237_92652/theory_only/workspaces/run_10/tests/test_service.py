import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.repository import Base, Repository, ReservationModel
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    yield db_session
    db_session.close()


@pytest.fixture
def service(db):
    repository = Repository(db)
    return CommerceService(repository)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result.sku == "SKU001"
    assert result.available_stock == 100


def test_adjust_stock_positive(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", 10)
    assert result.available_stock == 110


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -10)
    assert result.available_stock == 90


def test_adjust_stock_not_found(service):
    with pytest.raises(ValueError, match="SKU .* not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 10, "key1")
    assert result.sku == "SKU001"
    assert result.quantity == 10
    assert result.status == "PENDING"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 5)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 10, "key1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 10, "key1")
    result2 = service.create_reservation("SKU001", 10, "key1")
    assert result1.id == result2.id
    # Verify stock was only deducted once
    sku = service.repository.get_sku("SKU001")
    assert sku.available_stock == 90


def test_create_reservation_deducts_stock(service):
    service.create_sku("SKU001", 100)
    service.create_reservation("SKU001", 10, "key1")
    sku = service.repository.get_sku("SKU001")
    assert sku.available_stock == 90


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "key1")
    order = service.confirm_reservation(reservation.id)
    assert order.reservation_id == reservation.id
    # Verify status changed
    updated = service.repository.get_reservation(reservation.id)
    assert updated.status == "CONFIRMED"


def test_confirm_reservation_not_found(service):
    with pytest.raises(ValueError, match="Reservation not found"):
        service.confirm_reservation(999)


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "key1")
    service.confirm_reservation(reservation.id)
    # Try to confirm again
    with pytest.raises(ValueError, match="Reservation is not pending"):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "key1")
    result = service.cancel_reservation(reservation.id)
    assert result.status == "CANCELLED"


def test_cancel_reservation_restores_stock(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "key1")
    service.cancel_reservation(reservation.id)
    sku = service.repository.get_sku("SKU001")
    assert sku.available_stock == 100


def test_cancel_reservation_not_found(service):
    with pytest.raises(ValueError, match="Reservation not found"):
        service.cancel_reservation(999)


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "key1")
    service.confirm_reservation(reservation.id)
    with pytest.raises(ValueError, match="Reservation is not pending"):
        service.cancel_reservation(reservation.id)


def test_list_orders_empty(service):
    orders, total, page, size = service.list_orders(1, 10)
    assert len(orders) == 0
    assert total == 0


def test_list_orders_with_data(service):
    service.create_sku("SKU001", 100)
    reservation = service.create_reservation("SKU001", 10, "key1")
    service.confirm_reservation(reservation.id)
    orders, total, page, size = service.list_orders(1, 10)
    assert len(orders) == 1
    assert total == 1
    assert page == 1
    assert size == 10


def test_list_orders_pagination(service):
    service.create_sku("SKU001", 1000)
    # Create 25 orders
    for i in range(25):
        res = service.create_reservation("SKU001", 1, f"key{i}")
        service.confirm_reservation(res.id)

    # Page 1, size 10
    orders, total, page, size = service.list_orders(1, 10)
    assert len(orders) == 10
    assert total == 25
    assert page == 1

    # Page 2, size 10
    orders, total, page, size = service.list_orders(2, 10)
    assert len(orders) == 10
    assert total == 25
    assert page == 2

    # Page 3, size 10 (last page with 5 items)
    orders, total, page, size = service.list_orders(3, 10)
    assert len(orders) == 5
    assert total == 25
    assert page == 3
