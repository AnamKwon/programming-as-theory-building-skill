import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def repo(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKU:
    def test_create_sku(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", "A blue widget", 100)
        assert sku.id is not None
        assert sku.sku_code == "WIDGET-001"
        assert sku.stock_level == 100

    def test_create_sku_duplicate_code(self, service):
        service.create_sku("WIDGET-001", "Blue Widget", "A blue widget", 100)
        with pytest.raises(ValueError, match="already exists"):
            service.create_sku("WIDGET-001", "Another Widget", "Different", 50)

    def test_adjust_stock_positive(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        adjusted = service.adjust_stock(sku.id, 50)
        assert adjusted.stock_level == 150

    def test_adjust_stock_negative(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        adjusted = service.adjust_stock(sku.id, -30)
        assert adjusted.stock_level == 70

    def test_adjust_stock_below_zero(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 10)
        with pytest.raises(ValueError, match="below zero"):
            service.adjust_stock(sku.id, -20)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        res = service.create_reservation("order-001", sku.id, 10, "req-001")

        assert res.id is not None
        assert res.status == ReservationStatus.PENDING
        assert res.quantity == 10
        assert res.expires_at > datetime.utcnow()

        # Verify stock was reduced
        updated_sku = service.repo.get_sku(sku.id)
        assert updated_sku.stock_level == 90

    def test_create_reservation_insufficient_stock(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 10)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("order-001", sku.id, 20, "req-001")

    def test_reservation_idempotency(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        res1 = service.create_reservation("order-001", sku.id, 10, "req-001")
        res2 = service.create_reservation("order-001", sku.id, 10, "req-001")

        assert res1.id == res2.id
        # Stock should only be reduced once
        updated_sku = service.repo.get_sku(sku.id)
        assert updated_sku.stock_level == 90

    def test_confirm_reservation(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        res = service.create_reservation("order-001", sku.id, 10, "req-001")
        confirmed = service.confirm_reservation(res.id)

        assert confirmed.status == ReservationStatus.CONFIRMED

    def test_confirm_expired_reservation(self, service, repo):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        res = service.create_reservation("order-001", sku.id, 10, "req-001")

        # Manually expire the reservation
        res_from_db = repo.get_reservation(res.id)
        res_from_db.expires_at = datetime.utcnow() - timedelta(minutes=1)
        repo.session.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.id)

    def test_cancel_reservation(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        res = service.create_reservation("order-001", sku.id, 10, "req-001")
        cancelled = service.cancel_reservation(res.id)

        assert cancelled.status == ReservationStatus.CANCELLED
        # Stock should be released
        updated_sku = service.repo.get_sku(sku.id)
        assert updated_sku.stock_level == 100

    def test_confirm_cancelled_reservation(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        res = service.create_reservation("order-001", sku.id, 10, "req-001")
        service.cancel_reservation(res.id)

        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(res.id)


class TestOrder:
    def test_get_order(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 100)
        service.create_reservation("order-001", sku.id, 10, "req-001")
        order = service.get_order("order-001")

        assert order.id == "order-001"
        assert order.total_items == 10

    def test_list_orders_pagination(self, service):
        sku = service.create_sku("WIDGET-001", "Blue Widget", None, 1000)
        for i in range(5):
            service.create_reservation(f"order-{i:03d}", sku.id, 10, f"req-{i:03d}")

        orders, total = service.list_orders(limit=2, offset=0)
        assert len(orders) == 2
        assert total == 5

        orders_page2, total2 = service.list_orders(limit=2, offset=2)
        assert len(orders_page2) == 2
        assert total2 == 5
