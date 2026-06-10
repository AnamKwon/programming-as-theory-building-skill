import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import (
    Base,
    ReservationStatus,
    OrderStatus,
)
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
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
    return CommerceService(db_session)


class TestSKUCreation:
    def test_create_sku(self, service):
        sku = service.create_sku(name="Widget", initial_stock=100)
        assert sku.name == "Widget"
        assert sku.current_stock == 100
        assert sku.id is not None

    def test_create_sku_with_zero_stock(self, service):
        sku = service.create_sku(name="Gadget")
        assert sku.current_stock == 0


class TestStockAdjustment:
    def test_adjust_stock_increase(self, service):
        sku = service.create_sku(name="Product", initial_stock=10)
        updated = service.adjust_stock(sku.id, 5)
        assert updated.current_stock == 15

    def test_adjust_stock_decrease(self, service):
        sku = service.create_sku(name="Product", initial_stock=10)
        updated = service.adjust_stock(sku.id, -3)
        assert updated.current_stock == 7

    def test_adjust_stock_insufficient(self, service):
        sku = service.create_sku(name="Product", initial_stock=5)
        with pytest.raises(InsufficientStockError):
            service.adjust_stock(sku.id, -10)

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("nonexistent", 5)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        sku = service.create_sku(name="Item", initial_stock=50)
        res = service.create_reservation(sku.id, quantity=10)
        assert res.sku_id == sku.id
        assert res.quantity == 10
        assert res.status == ReservationStatus.PENDING
        assert res.id is not None

        # Stock should be reduced
        updated_sku = service.sku_repo.get(sku.id)
        assert updated_sku.current_stock == 40

    def test_create_reservation_insufficient_stock(self, service):
        sku = service.create_sku(name="Item", initial_stock=5)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(sku.id, quantity=10)

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("nonexistent", quantity=5)

    def test_idempotent_reservation(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        key = "idempotency-key-1"
        res1 = service.create_reservation(sku.id, quantity=10, idempotency_key=key)
        res2 = service.create_reservation(sku.id, quantity=10, idempotency_key=key)
        assert res1.id == res2.id
        # Stock should only be reserved once
        updated_sku = service.sku_repo.get(sku.id)
        assert updated_sku.current_stock == 90

    def test_reservation_expiry(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=10)
        # Mark as expired manually by checking expiry logic
        assert res.expires_at > datetime.now()


class TestReservationConfirmation:
    def test_confirm_reservation(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=15)
        order = service.confirm_reservation(res.id)
        assert order.id is not None
        assert order.reservation_id == res.id
        assert order.quantity == 15
        assert order.status == OrderStatus.CONFIRMED

        # Check reservation marked as confirmed
        updated_res = service.reservation_repo.get(res.id)
        assert updated_res.status == ReservationStatus.CONFIRMED

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("nonexistent")

    def test_confirm_expired_reservation(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=10)
        # Manually set expiry to past
        res.expires_at = datetime.now() - timedelta(minutes=1)
        service.session.commit()
        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.id)

    def test_confirm_already_confirmed(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=10)
        service.confirm_reservation(res.id)
        with pytest.raises(ValueError):
            service.confirm_reservation(res.id)


class TestReservationCancellation:
    def test_cancel_reservation(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=20)
        assert service.sku_repo.get(sku.id).current_stock == 80

        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == ReservationStatus.CANCELLED

        # Stock should be released
        assert service.sku_repo.get(sku.id).current_stock == 100

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("nonexistent")

    def test_cancel_confirmed_reservation(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=10)
        service.confirm_reservation(res.id)
        with pytest.raises(ValueError):
            service.cancel_reservation(res.id)


class TestOrderLookup:
    def test_get_order(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=15)
        order = service.confirm_reservation(res.id)
        fetched = service.get_order(order.id)
        assert fetched.id == order.id

    def test_get_nonexistent_order(self, service):
        with pytest.raises(ValueError):
            service.get_order("nonexistent")

    def test_list_orders_pagination(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        # Create multiple orders
        for i in range(5):
            res = service.create_reservation(sku.id, quantity=1)
            service.confirm_reservation(res.id)

        # Test pagination
        orders, total = service.list_orders(limit=2, offset=0)
        assert len(orders) == 2
        assert total == 5

        orders, total = service.list_orders(limit=2, offset=2)
        assert len(orders) == 2

        orders, total = service.list_orders(limit=2, offset=4)
        assert len(orders) == 1


class TestExpirationCleanup:
    def test_expire_old_reservations(self, service):
        sku = service.create_sku(name="Item", initial_stock=100)
        res = service.create_reservation(sku.id, quantity=10)
        # Manually mark as expired
        res.expires_at = datetime.now() - timedelta(minutes=1)
        service.session.commit()

        assert service.sku_repo.get(sku.id).current_stock == 90
        expired_count = service.expire_old_reservations()
        assert expired_count == 1
        # Stock should be released
        assert service.sku_repo.get(sku.id).current_stock == 100
