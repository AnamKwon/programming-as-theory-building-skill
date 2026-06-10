import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, OrderStatus
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.fixture
def repository(in_memory_db):
    repo = Repository(database_url="sqlite:///:memory:")
    repo.SessionLocal = lambda: in_memory_db
    return repo


@pytest.fixture
def service(repository):
    return CommerceService(repository)


@pytest.fixture
def session(in_memory_db):
    return in_memory_db


class TestSKUOperations:
    def test_create_sku(self, service, session):
        sku = service.create_sku(session, "SKU-001", 100)
        assert sku.id == "SKU-001"
        assert sku.total_stock == 100
        assert sku.available_stock == 100
        assert sku.reserved_stock == 0

    def test_create_duplicate_sku_fails(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        with pytest.raises(ValueError, match="already exists"):
            service.create_sku(session, "SKU-001", 50)

    def test_adjust_stock_positive(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        sku = service.adjust_stock(session, "SKU-001", 50)
        assert sku.total_stock == 150

    def test_adjust_stock_negative(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        sku = service.adjust_stock(session, "SKU-001", -30)
        assert sku.total_stock == 70

    def test_adjust_stock_below_zero_fails(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        with pytest.raises(ValueError, match="negative"):
            service.adjust_stock(session, "SKU-001", -150)

    def test_adjust_nonexistent_sku_fails(self, service, session):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock(session, "SKU-999", 10)


class TestReservations:
    def test_create_reservation_success(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        assert reservation.sku_id == "SKU-001"
        assert reservation.quantity == 30
        assert reservation.status == "active"
        assert reservation.is_expired() is False

    def test_create_reservation_insufficient_stock(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation(session, "SKU-001", 150)

    def test_create_reservation_nonexistent_sku(self, service, session):
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation(session, "SKU-999", 10)

    def test_reservation_reserves_stock(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        service.create_reservation(session, "SKU-001", 30)

        sku = service.repo.get_sku(session, "SKU-001")
        assert sku.reserved_stock == 30
        assert sku.available_stock == 70

    def test_idempotent_reservation(self, service, session):
        service.create_sku(session, "SKU-001", 100)

        res1 = service.create_reservation(session, "SKU-001", 20, idempotency_key="key-1")
        res2 = service.create_reservation(session, "SKU-001", 999, idempotency_key="key-1")

        assert res1.id == res2.id
        assert res2.quantity == 20  # unchanged
        sku = service.repo.get_sku(session, "SKU-001")
        assert sku.reserved_stock == 20  # not double-reserved

    def test_confirm_reservation_creates_order(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        order = service.confirm_reservation(session, reservation.id)

        assert order.sku_id == "SKU-001"
        assert order.quantity == 30
        assert order.status == "confirmed"
        assert order.reservation_id == reservation.id

    def test_confirm_reservation_updates_stock(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        service.confirm_reservation(session, reservation.id)

        sku = service.repo.get_sku(session, "SKU-001")
        assert sku.reserved_stock == 0
        assert sku.sold_stock == 30
        assert sku.available_stock == 70

    def test_confirm_expired_reservation_fails(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        # Manually expire the reservation
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(session, reservation.id)

    def test_confirm_nonexistent_reservation_fails(self, service, session):
        with pytest.raises(ValueError, match="not found"):
            service.confirm_reservation(session, "RES-999")

    def test_cancel_reservation_success(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        cancelled = service.cancel_reservation(session, reservation.id)

        assert cancelled.status == "cancelled"

    def test_cancel_reservation_releases_stock(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        service.cancel_reservation(session, reservation.id)

        sku = service.repo.get_sku(session, "SKU-001")
        assert sku.reserved_stock == 0
        assert sku.available_stock == 100

    def test_cancel_already_cancelled_is_idempotent(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)

        service.cancel_reservation(session, reservation.id)
        result = service.cancel_reservation(session, reservation.id)

        assert result.status == "cancelled"
        sku = service.repo.get_sku(session, "SKU-001")
        assert sku.reserved_stock == 0


class TestOrders:
    def test_list_orders_empty(self, service, session):
        orders, total = service.list_orders(session, page=1, page_size=20)
        assert len(orders) == 0
        assert total == 0

    def test_list_orders_pagination(self, service, session):
        service.create_sku(session, "SKU-001", 1000)
        for i in range(25):
            reservation = service.create_reservation(session, "SKU-001", 10)
            service.confirm_reservation(session, reservation.id)

        page1, total = service.list_orders(session, page=1, page_size=10)
        page2, _ = service.list_orders(session, page=2, page_size=10)
        page3, _ = service.list_orders(session, page=3, page_size=10)

        assert len(page1) == 10
        assert len(page2) == 10
        assert len(page3) == 5
        assert total == 25

    def test_list_orders_invalid_page_fails(self, service, session):
        with pytest.raises(ValueError, match="Page must be >= 1"):
            service.list_orders(session, page=0, page_size=20)

    def test_list_orders_invalid_page_size_fails(self, service, session):
        with pytest.raises(ValueError, match="Page size must be between"):
            service.list_orders(session, page=1, page_size=0)

        with pytest.raises(ValueError, match="Page size must be between"):
            service.list_orders(session, page=1, page_size=101)

    def test_get_order(self, service, session):
        service.create_sku(session, "SKU-001", 100)
        reservation = service.create_reservation(session, "SKU-001", 30)
        order = service.confirm_reservation(session, reservation.id)

        retrieved = service.get_order(session, order.id)

        assert retrieved.id == order.id
        assert retrieved.sku_id == "SKU-001"
        assert retrieved.status == "confirmed"

    def test_get_nonexistent_order_returns_none(self, service, session):
        order = service.get_order(session, "ORDER-999")
        assert order is None
