import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.commerce_service.models import Base, ReservationModel
from src.commerce_service.service import Service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def test_create_sku(db):
    service = Service(db)
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku == "SKU-001"
    assert sku.stock == 100


def test_adjust_stock(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    sku = service.adjust_stock("SKU-001", 10)
    assert sku.stock == 110

    sku = service.adjust_stock("SKU-001", -20)
    assert sku.stock == 90


def test_reserve_stock_success(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    reservation = service.reserve_stock("SKU-001", 20, "idempotency-1")
    assert reservation.id is not None
    assert reservation.sku == "SKU-001"
    assert reservation.quantity == 20
    assert reservation.status == "PENDING"

    # Check stock was deducted
    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.stock == 80


def test_reserve_stock_insufficient(db):
    service = Service(db)
    service.create_sku("SKU-001", 10)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.reserve_stock("SKU-001", 20, "idempotency-1")


def test_reserve_stock_idempotency(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    # First reservation
    res1 = service.reserve_stock("SKU-001", 20, "idempotency-1")

    # Second with same key should return same reservation
    res2 = service.reserve_stock("SKU-001", 20, "idempotency-1")
    assert res1.id == res2.id

    # Stock should only be deducted once
    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.stock == 80


def test_confirm_reservation_success(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    reservation = service.reserve_stock("SKU-001", 20, "idempotency-1")
    order = service.confirm_reservation(reservation.id)

    assert order.id is not None
    assert order.created_at is not None

    # Check reservation status
    updated_reservation = service.repo.get_reservation(reservation.id)
    assert updated_reservation.status == "CONFIRMED"


def test_confirm_reservation_expired(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    reservation = service.reserve_stock("SKU-001", 20, "idempotency-1")

    # Manually set created_at to more than 300 seconds ago
    old_time = datetime.utcnow() - timedelta(seconds=310)
    db.query(ReservationModel).filter(
        ReservationModel.id == reservation.id
    ).update({"created_at": old_time})
    db.commit()

    # Try to confirm should fail
    with pytest.raises(ValueError, match="Reservation expired"):
        service.confirm_reservation(reservation.id)

    # Check reservation is marked as EXPIRED
    updated = service.repo.get_reservation(reservation.id)
    assert updated.status == "EXPIRED"

    # Check stock was restored
    assert service.repo.get_sku_by_name("SKU-001").stock == 100


def test_confirm_non_pending_reservation(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    reservation = service.reserve_stock("SKU-001", 20, "idempotency-1")
    service.confirm_reservation(reservation.id)

    # Try to confirm again should fail
    with pytest.raises(ValueError, match="Cannot confirm"):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation_success(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    reservation = service.reserve_stock("SKU-001", 20, "idempotency-1")
    assert service.repo.get_sku_by_name("SKU-001").stock == 80

    result = service.cancel_reservation(reservation.id)
    assert result.status == "CANCELLED"

    # Check stock was restored
    assert service.repo.get_sku_by_name("SKU-001").stock == 100


def test_cancel_non_pending_reservation(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    reservation = service.reserve_stock("SKU-001", 20, "idempotency-1")
    service.confirm_reservation(reservation.id)

    # Try to cancel should fail
    with pytest.raises(ValueError, match="Cannot cancel"):
        service.cancel_reservation(reservation.id)


def test_get_orders_pagination(db):
    service = Service(db)
    service.create_sku("SKU-001", 100)

    # Create and confirm multiple reservations
    for i in range(15):
        reservation = service.reserve_stock("SKU-001", 1, f"idempotency-{i}")
        service.confirm_reservation(reservation.id)

    # Test page 1
    page1 = service.get_orders(page=1, size=10)
    assert len(page1.items) == 10
    assert page1.page == 1
    assert page1.size == 10
    assert page1.total == 15

    # Test page 2
    page2 = service.get_orders(page=2, size=10)
    assert len(page2.items) == 5
    assert page2.page == 2
    assert page2.total == 15
