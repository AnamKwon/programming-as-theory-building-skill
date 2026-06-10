import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
    IdempotencyError,
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
def service(db_session):
    return Service(db_session)


class TestSKU:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU001", "Widget", 100)
        assert sku.id == "SKU001"
        assert sku.name == "Widget"
        assert sku.stock_quantity == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU001", "Widget", 100)
        sku = service.adjust_stock("SKU001", 50)
        assert sku.stock_quantity == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", "Widget", 100)
        sku = service.adjust_stock("SKU001", -30)
        assert sku.stock_quantity == 70

    def test_adjust_stock_insufficient(self, service):
        service.create_sku("SKU001", "Widget", 10)
        with pytest.raises(ValueError):
            service.adjust_stock("SKU001", -20)

    def test_adjust_stock_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU001", "Widget", 100)
        reservation = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        assert reservation.sku_id == "SKU001"
        assert reservation.quantity == 50
        assert reservation.status == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Widget", 30)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")

    def test_create_reservation_accounts_for_existing_reservations(self, service):
        service.create_sku("SKU001", "Widget", 100)
        service.create_reservation("SKU001", 60, "IDEMPOTENCY_1")
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 50, "IDEMPOTENCY_2")

    def test_create_reservation_idempotent(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res1 = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        res2 = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        assert res1.id == res2.id

    def test_create_reservation_idempotency_key_conflict(self, service):
        service.create_sku("SKU001", "Widget", 100)
        service.create_sku("SKU002", "Gadget", 100)
        service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        with pytest.raises(IdempotencyError):
            service.create_reservation("SKU002", 50, "IDEMPOTENCY_1")

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", 50, "IDEMPOTENCY_1")

    def test_cancel_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == ReservationStatus.CANCELLED

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")


class TestOrder:
    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        order = service.confirm_reservation(res.id)
        assert order.reservation_id == res.id
        assert order.status == OrderStatus.CONFIRMED

    def test_confirm_reservation_expired(self, service, db_session):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")

        from commerce_service.repository import Repository
        repo = Repository(db_session)
        res_orm = repo.get_reservation(res.id)
        res_orm.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db_session.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.id)

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_list_orders(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res1 = service.create_reservation("SKU001", 50, "IDEMPOTENCY_1")
        res2 = service.create_reservation("SKU001", 30, "IDEMPOTENCY_2")

        service.confirm_reservation(res1.id)
        service.confirm_reservation(res2.id)

        orders, total = service.list_orders(limit=10, offset=0)
        assert total == 2
        assert len(orders) == 2
