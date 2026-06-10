"""Tests for the service layer."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidReservationStatusError,
    NotFoundError,
    ReservationExpiredError,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create a service instance with test database."""
    return CommerceService(db_session)


class TestSkuOperations:
    """Tests for SKU operations."""

    def test_create_sku(self, service):
        """Test creating a SKU."""
        sku = service.create_sku("PROD001", initial_stock=100)
        assert sku.id is not None
        assert sku.sku_code == "PROD001"
        assert sku.stock_quantity == 100

    def test_create_sku_default_stock(self, service):
        """Test creating a SKU with default stock (0)."""
        sku = service.create_sku("PROD002")
        assert sku.stock_quantity == 0

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        sku = service.create_sku("PROD003", initial_stock=50)
        adjusted = service.adjust_stock(sku.id, 25)
        assert adjusted.stock_quantity == 75

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        sku = service.create_sku("PROD004", initial_stock=100)
        adjusted = service.adjust_stock(sku.id, -30)
        assert adjusted.stock_quantity == 70

    def test_adjust_stock_sku_not_found(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(NotFoundError):
            service.adjust_stock(999, 10)

    def test_adjust_stock_negative_result(self, service):
        """Test that stock cannot go negative."""
        sku = service.create_sku("PROD005", initial_stock=10)
        with pytest.raises(ValueError):
            service.adjust_stock(sku.id, -20)


class TestReservations:
    """Tests for reservation operations."""

    def test_create_reservation_success(self, service):
        """Test creating a reservation with sufficient stock."""
        sku = service.create_sku("PROD006", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-1",
            ttl_seconds=3600,
        )
        assert reservation.id is not None
        assert reservation.sku_id == sku.id
        assert reservation.quantity == 30
        assert reservation.status == "PENDING"
        assert sku.stock_quantity == 70  # Stock should be deducted

    def test_create_reservation_insufficient_stock(self, service):
        """Test creating a reservation with insufficient stock."""
        sku = service.create_sku("PROD007", initial_stock=10)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(
                sku_id=sku.id,
                quantity=20,
                idempotency_key="idempotency-key-2",
            )

    def test_create_reservation_sku_not_found(self, service):
        """Test creating a reservation for non-existent SKU."""
        with pytest.raises(NotFoundError):
            service.create_reservation(
                sku_id=999,
                quantity=10,
                idempotency_key="idempotency-key-3",
            )

    def test_create_reservation_idempotency(self, service):
        """Test idempotent reservation creation."""
        sku = service.create_sku("PROD008", initial_stock=100)
        key = "idempotency-key-4"

        res1 = service.create_reservation(
            sku_id=sku.id,
            quantity=25,
            idempotency_key=key,
        )

        res2 = service.create_reservation(
            sku_id=sku.id,
            quantity=25,
            idempotency_key=key,
        )

        assert res1.id == res2.id
        assert sku.stock_quantity == 75  # Stock deducted only once

    def test_create_reservation_expired_key_reuse(self, service):
        """Test that reusing an idempotency key from an expired reservation raises error."""
        sku = service.create_sku("PROD009", initial_stock=100)
        key = "idempotency-key-5"

        res = service.create_reservation(
            sku_id=sku.id,
            quantity=25,
            idempotency_key=key,
            ttl_seconds=1,
        )

        res.status = "EXPIRED"
        service.session.commit()

        with pytest.raises(ValueError, match="already used"):
            service.create_reservation(
                sku_id=sku.id,
                quantity=25,
                idempotency_key=key,
            )

    def test_confirm_reservation_success(self, service):
        """Test confirming a pending reservation."""
        sku = service.create_sku("PROD010", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-6",
        )

        confirmed_res, order = service.confirm_reservation(reservation.id)
        assert confirmed_res.status == "CONFIRMED"
        assert order.id is not None
        assert order.status == "CONFIRMED"

    def test_confirm_reservation_not_found(self, service):
        """Test confirming non-existent reservation."""
        with pytest.raises(NotFoundError):
            service.confirm_reservation(999)

    def test_confirm_reservation_already_confirmed(self, service):
        """Test confirming an already-confirmed reservation."""
        sku = service.create_sku("PROD011", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-7",
        )

        service.confirm_reservation(reservation.id)

        with pytest.raises(InvalidReservationStatusError):
            service.confirm_reservation(reservation.id)

    def test_confirm_reservation_expired(self, service):
        """Test confirming an expired reservation."""
        sku = service.create_sku("PROD012", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-8",
            ttl_seconds=-1,  # Already expired
        )

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation.id)

        db_reservation = service.reservation_repo.get_by_id(reservation.id)
        assert db_reservation.status == "EXPIRED"

    def test_cancel_reservation_pending(self, service):
        """Test cancelling a pending reservation."""
        sku = service.create_sku("PROD013", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-9",
        )

        initial_stock = sku.stock_quantity  # Should be 70

        cancelled = service.cancel_reservation(reservation.id)
        assert cancelled.status == "CANCELLED"
        assert sku.stock_quantity == initial_stock + 30  # Stock restored

    def test_cancel_reservation_confirmed(self, service):
        """Test cancelling a confirmed reservation."""
        sku = service.create_sku("PROD014", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-10",
        )
        service.confirm_reservation(reservation.id)

        initial_stock = sku.stock_quantity

        cancelled = service.cancel_reservation(reservation.id)
        assert cancelled.status == "CANCELLED"
        assert sku.stock_quantity == initial_stock + 30  # Stock restored

        order = service.order_repo.get_by_reservation_id(reservation.id)
        assert order.status == "CANCELLED"

    def test_cancel_reservation_not_found(self, service):
        """Test cancelling non-existent reservation."""
        with pytest.raises(NotFoundError):
            service.cancel_reservation(999)

    def test_cancel_reservation_already_cancelled(self, service):
        """Test cancelling an already-cancelled reservation."""
        sku = service.create_sku("PROD015", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-11",
        )

        service.cancel_reservation(reservation.id)

        with pytest.raises(InvalidReservationStatusError):
            service.cancel_reservation(reservation.id)


class TestOrders:
    """Tests for order operations."""

    def test_get_order(self, service):
        """Test retrieving an order."""
        sku = service.create_sku("PROD016", initial_stock=100)
        reservation = service.create_reservation(
            sku_id=sku.id,
            quantity=30,
            idempotency_key="idempotency-key-12",
        )
        _, order = service.confirm_reservation(reservation.id)

        retrieved = service.get_order(order.id)
        assert retrieved.id == order.id
        assert retrieved.status == "CONFIRMED"

    def test_get_order_not_found(self, service):
        """Test retrieving non-existent order."""
        with pytest.raises(NotFoundError):
            service.get_order(999)

    def test_list_orders_pagination(self, service):
        """Test paginating through orders."""
        sku = service.create_sku("PROD017", initial_stock=1000)

        for i in range(15):
            res = service.create_reservation(
                sku_id=sku.id,
                quantity=10,
                idempotency_key=f"idempotency-key-{i}",
            )
            service.confirm_reservation(res.id)

        orders, total, has_more = service.list_orders(limit=10, offset=0)
        assert len(orders) == 10
        assert total == 15
        assert has_more is True

        orders_page2, total2, has_more2 = service.list_orders(limit=10, offset=10)
        assert len(orders_page2) == 5
        assert total2 == 15
        assert has_more2 is False
