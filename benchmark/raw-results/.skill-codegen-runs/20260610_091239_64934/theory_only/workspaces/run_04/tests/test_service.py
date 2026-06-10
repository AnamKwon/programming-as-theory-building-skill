import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
    IdempotencyViolationError,
    ServiceError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


class TestSKUAndStock:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU001", "Test Product", 99.99)
        assert sku.sku == "SKU001"
        assert sku.name == "Test Product"
        assert sku.base_price == 99.99

    def test_create_duplicate_sku_raises_error(self, service):
        service.create_sku("SKU001", "Product 1", 10.0)
        with pytest.raises(ServiceError, match="already exists"):
            service.create_sku("SKU001", "Product 2", 20.0)

    def test_adjust_stock(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        stock = service.adjust_stock(sku.id, 100)
        assert stock.quantity == 100

        stock = service.adjust_stock(sku.id, -30)
        assert stock.quantity == 70

    def test_adjust_stock_nonexistent_sku_raises_error(self, service):
        with pytest.raises(ServiceError, match="not found"):
            service.adjust_stock(999, 10)

    def test_negative_stock_raises_error(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 50)
        with pytest.raises(ServiceError, match="cannot be negative"):
            service.adjust_stock(sku.id, -100)

    def test_get_stock(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        stock = service.get_stock(sku.id)
        assert stock.quantity == 100


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)

        reservation, is_idempotent = service.create_reservation(
            sku_id=sku.id, quantity=10
        )
        assert reservation.sku_id == sku.id
        assert reservation.quantity == 10
        assert reservation.status == ReservationStatus.PENDING
        assert is_idempotent is False

    def test_create_reservation_insufficient_stock(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 50)

        with pytest.raises(InsufficientStockError):
            service.create_reservation(sku_id=sku.id, quantity=100)

    def test_create_reservation_with_idempotency_key(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)

        idempotency_key = "test-idempotency-001"
        res1, is_idempotent1 = service.create_reservation(
            sku_id=sku.id,
            quantity=10,
            idempotency_key=idempotency_key,
        )
        assert is_idempotent1 is False

        # Retry with same key should return same reservation
        res2, is_idempotent2 = service.create_reservation(
            sku_id=sku.id,
            quantity=10,
            idempotency_key=idempotency_key,
        )
        assert res2.id == res1.id
        assert is_idempotent2 is True

    def test_create_reservation_idempotency_key_conflict(self, service):
        sku1 = service.create_sku("SKU001", "Product 1", 10.0)
        sku2 = service.create_sku("SKU002", "Product 2", 10.0)
        service.adjust_stock(sku1.id, 100)
        service.adjust_stock(sku2.id, 100)

        idempotency_key = "test-key"
        service.create_reservation(
            sku_id=sku1.id, quantity=10, idempotency_key=idempotency_key
        )

        # Retry with same key but different params should fail
        with pytest.raises(IdempotencyViolationError):
            service.create_reservation(
                sku_id=sku2.id, quantity=10, idempotency_key=idempotency_key
            )

    def test_confirm_reservation(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        res, _ = service.create_reservation(sku_id=sku.id, quantity=10)

        confirmed = service.confirm_reservation(res.id)
        assert confirmed.status == ReservationStatus.CONFIRMED

    def test_confirm_expired_reservation(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        res, _ = service.create_reservation(sku_id=sku.id, quantity=10, ttl_seconds=0)

        # Manually set expiration in the past
        res.expires_at = datetime.utcnow() - timedelta(seconds=1)
        service.db.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.id)

    def test_cancel_reservation(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        res, _ = service.create_reservation(sku_id=sku.id, quantity=10)

        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == ReservationStatus.CANCELLED

    def test_cancel_confirmed_reservation_raises_error(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        res, _ = service.create_reservation(sku_id=sku.id, quantity=10)
        service.confirm_reservation(res.id)

        with pytest.raises(InvalidStateTransitionError):
            service.cancel_reservation(res.id)

    def test_get_nonexistent_reservation_raises_error(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.get_reservation(999)


class TestOrders:
    def test_order_created_with_reservation(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        res, _ = service.create_reservation(sku_id=sku.id, quantity=10)

        order = service.repo.get_order_by_reservation(res.id)
        assert order is not None
        assert order.status == OrderStatus.PENDING
        assert order.quantity_reserved == 10

    def test_list_orders_with_pagination(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 500)

        for i in range(15):
            service.create_reservation(sku_id=sku.id, quantity=10)

        orders, total = service.list_orders(page=1, page_size=10)
        assert len(orders) == 10
        assert total == 15

        orders_page2, _ = service.list_orders(page=2, page_size=10)
        assert len(orders_page2) == 5

    def test_get_order(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)
        res, _ = service.create_reservation(sku_id=sku.id, quantity=10)
        order = service.repo.get_order_by_reservation(res.id)

        fetched = service.get_order(order.id)
        assert fetched.id == order.id
        assert fetched.quantity_reserved == 10


class TestStockAndReservationInteraction:
    def test_multiple_pending_reservations_reduce_available_stock(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)

        # First reservation takes 30
        res1, _ = service.create_reservation(sku_id=sku.id, quantity=30)
        # Second reservation should see 70 available
        res2, _ = service.create_reservation(sku_id=sku.id, quantity=70)
        # Third should fail (0 available)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(sku_id=sku.id, quantity=1)

    def test_confirmed_then_canceled_release_availability(self, service):
        sku = service.create_sku("SKU001", "Product", 10.0)
        service.adjust_stock(sku.id, 100)

        res, _ = service.create_reservation(sku_id=sku.id, quantity=50)
        service.confirm_reservation(res.id)

        # After confirm, the confirmed reservation doesn't count as pending
        # So we can still reserve the other 50
        res2, _ = service.create_reservation(sku_id=sku.id, quantity=50)
        assert res2.quantity == 50

        # Cancel res2, should be able to reserve again
        service.cancel_reservation(res2.id)
        res3, _ = service.create_reservation(sku_id=sku.id, quantity=50)
        assert res3.quantity == 50
