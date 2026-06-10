import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationExpiredError,
    IdempotencyError,
    InvalidStateError,
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
def repository(db):
    return Repository(db)


@pytest.fixture
def service(repository):
    return Service(repository)


class TestSKUManagement:
    def test_create_sku(self, service):
        sku = service.create_sku("PROD-001", 100)
        assert sku.sku_id == "PROD-001"
        assert sku.quantity == 100

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("PROD-001", 100)
        with pytest.raises(ValueError, match="already exists"):
            service.create_sku("PROD-001", 50)

    def test_adjust_stock(self, service):
        service.create_sku("PROD-001", 100)
        sku = service.adjust_stock("PROD-001", -30)
        assert sku.quantity == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock("PROD-999", 10)


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)
        assert reservation.sku_id == "PROD-001"
        assert reservation.quantity == 50
        assert reservation.status == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("PROD-001", 30)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("PROD-001", 50)

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation("PROD-999", 10)

    def test_idempotent_reservation_retry(self, service):
        service.create_sku("PROD-001", 100)
        res1 = service.create_reservation("PROD-001", 50, idempotency_key="idem-key-1")
        res2 = service.create_reservation("PROD-001", 50, idempotency_key="idem-key-1")
        assert res1.reservation_id == res2.reservation_id

    def test_idempotent_key_different_quantities(self, service):
        service.create_sku("PROD-001", 100)
        res1 = service.create_reservation("PROD-001", 50, idempotency_key="idem-key-1")
        res2 = service.create_reservation("PROD-001", 30, idempotency_key="idem-key-1")
        assert res1.reservation_id == res2.reservation_id
        assert res2.quantity == 50

    def test_expired_reservation_rejected(self, service, repository):
        from datetime import datetime, timedelta
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)

        # Manually set the reservation to have expired
        res_record = repository.get_reservation(reservation.reservation_id)
        res_record.expires_at = datetime.utcnow() - timedelta(seconds=10)
        repository.session.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation.reservation_id)

    def test_cancel_pending_reservation(self, service):
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)
        cancelled = service.cancel_reservation(reservation.reservation_id)
        assert cancelled.status == ReservationStatus.CANCELLED

    def test_cancel_confirmed_reservation_fails(self, service):
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)
        service.confirm_reservation(reservation.reservation_id)

        with pytest.raises(InvalidStateError, match="Cannot cancel a confirmed"):
            service.cancel_reservation(reservation.reservation_id)


class TestOrderConfirmation:
    def test_confirm_reservation_creates_order(self, service):
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)
        order = service.confirm_reservation(reservation.reservation_id)

        assert order.sku_id == "PROD-001"
        assert order.quantity == 50
        assert order.status == OrderStatus.PENDING
        assert order.reservation_id == reservation.reservation_id

    def test_confirm_reservation_deducts_stock(self, service):
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)
        service.confirm_reservation(reservation.reservation_id)

        sku = service.repo.get_sku("PROD-001")
        assert sku.quantity == 50

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.confirm_reservation("INVALID-RES-ID")

    def test_confirm_already_confirmed_reservation(self, service):
        service.create_sku("PROD-001", 100)
        reservation = service.create_reservation("PROD-001", 50)
        service.confirm_reservation(reservation.reservation_id)

        with pytest.raises(InvalidStateError, match="Cannot confirm"):
            service.confirm_reservation(reservation.reservation_id)


class TestOrderLookup:
    def test_list_orders_pagination(self, service):
        service.create_sku("PROD-001", 1000)

        order_ids = []
        for i in range(15):
            res = service.create_reservation("PROD-001", 10)
            order = service.confirm_reservation(res.reservation_id)
            order_ids.append(order.order_id)

        orders, next_cursor = service.list_orders(limit=10)
        assert len(orders) == 10
        assert next_cursor is not None

        orders2, next_cursor2 = service.list_orders(limit=10, cursor=next_cursor)
        assert len(orders2) == 5
        assert next_cursor2 is None

    def test_get_nonexistent_order(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.get_order("INVALID-ORDER-ID")
