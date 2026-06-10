import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    repo = Repository(db_session)
    return Service(repo)


class TestSKUCreation:
    def test_create_sku(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        sku = service.repo.get_sku("TEST-001")
        assert sku.sku == "TEST-001"
        assert sku.name == "Test Product"
        assert sku.total_stock == 100
        assert sku.reserved_stock == 0

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        with pytest.raises(Exception):
            service.create_sku("TEST-001", "Another", 50)


class TestStockAdjustment:
    def test_adjust_stock_positive(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        service.adjust_stock("TEST-001", 50)
        sku = service.repo.get_sku("TEST-001")
        assert sku.total_stock == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        service.adjust_stock("TEST-001", -30)
        sku = service.repo.get_sku("TEST-001")
        assert sku.total_stock == 70

    def test_adjust_stock_below_zero_fails(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        with pytest.raises(InsufficientStockError):
            service.adjust_stock("TEST-001", -150)

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(Exception):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    def test_create_reservation(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        assert res.quantity == 50
        assert res.status == ReservationStatus.PENDING
        sku = service.repo.get_sku("TEST-001")
        assert sku.reserved_stock == 50
        assert sku.total_stock == 100

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("TEST-001", "Test Product", 30)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("TEST-001", 50, "idempotency-key-1")

    def test_create_reservation_idempotent(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res1 = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        res2 = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        assert res1.reservation_id == res2.reservation_id
        sku = service.repo.get_sku("TEST-001")
        assert sku.reserved_stock == 50

    def test_cancel_reservation(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        service.cancel_reservation(res.reservation_id)
        sku = service.repo.get_sku("TEST-001")
        assert sku.reserved_stock == 0
        cancelled = service.repo.get_reservation(res.reservation_id)
        assert cancelled.status == ReservationStatus.CANCELLED

    def test_cannot_cancel_confirmed_reservation(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        service.confirm_reservation(res.reservation_id, "idempotency-key-1")
        with pytest.raises(Exception):
            service.cancel_reservation(res.reservation_id)

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("nonexistent-id")


class TestOrderConfirmation:
    def test_confirm_reservation(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        order = service.confirm_reservation(res.reservation_id, "idempotency-key-1")
        assert order.sku == "TEST-001"
        assert order.quantity == 50
        confirmed = service.repo.get_reservation(res.reservation_id)
        assert confirmed.status == ReservationStatus.CONFIRMED

    def test_confirm_reservation_idempotent(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        order1 = service.confirm_reservation(res.reservation_id, "idempotency-key-1")
        order2 = service.confirm_reservation(res.reservation_id, "idempotency-key-1")
        assert order1.order_id == order2.order_id

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("nonexistent-id", "idempotency-key")

    def test_confirm_expired_reservation(self, service, db_session):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        past = datetime.utcnow() - timedelta(minutes=1)
        db_res = service.repo.get_reservation(res.reservation_id)
        db_res.expires_at = past
        db_session.commit()
        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.reservation_id, "idempotency-key-1")


class TestOrderLookup:
    def test_get_order(self, service):
        service.create_sku("TEST-001", "Test Product", 100)
        res = service.create_reservation("TEST-001", 50, "idempotency-key-1")
        order = service.confirm_reservation(res.reservation_id, "idempotency-key-1")
        found = service.get_order(order.order_id)
        assert found.order_id == order.order_id
        assert found.sku == "TEST-001"
        assert found.quantity == 50

    def test_get_nonexistent_order(self, service):
        with pytest.raises(Exception):
            service.get_order("nonexistent-id")

    def test_list_orders_pagination(self, service):
        service.create_sku("TEST-001", "Test Product", 1000)
        for i in range(15):
            res = service.create_reservation("TEST-001", 10, f"idempotency-key-{i}")
            service.confirm_reservation(res.reservation_id, f"idempotency-key-{i}")

        orders1, total1 = service.list_orders(page=1, page_size=10)
        assert len(orders1) == 10
        assert total1 == 15

        orders2, total2 = service.list_orders(page=2, page_size=10)
        assert len(orders2) == 5
        assert total2 == 15
