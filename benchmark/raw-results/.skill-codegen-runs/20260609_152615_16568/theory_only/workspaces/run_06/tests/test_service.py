import pytest
import tempfile
import os
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidReservationStateError,
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    os.unlink(path)


@pytest.fixture
def repository(temp_db):
    """Create a repository with a temporary database."""
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    """Create a service with a temporary repository."""
    return CommerceService(repository)


class TestSKUManagement:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU001", 100)
        assert sku.id == "SKU001"
        assert sku.available_stock == 100
        assert sku.reserved_stock == 0

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU001", 100)
        sku = service.adjust_stock("SKU001", 50)
        assert sku.available_stock == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU001", 100)
        sku = service.adjust_stock("SKU001", -30)
        assert sku.available_stock == 70

    def test_adjust_stock_negative_fails(self, service):
        service.create_sku("SKU001", 100)
        with pytest.raises(ValueError, match="Stock cannot be negative"):
            service.adjust_stock("SKU001", -150)

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        reservation, is_new = service.create_reservation(
            "SKU001", 10, "idempotency-key-1"
        )
        assert reservation.id is not None
        assert reservation.quantity == 10
        assert is_new is True

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU001", 100)
        res1, is_new1 = service.create_reservation(
            "SKU001", 10, "idempotency-key-1"
        )
        res2, is_new2 = service.create_reservation(
            "SKU001", 10, "idempotency-key-1"
        )
        assert res1.id == res2.id
        assert is_new1 is True
        assert is_new2 is False

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 100, "idempotency-key-1")

    def test_create_reservation_respects_existing_reservations(self, service):
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 60, "key1")
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 50, "key2")

    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation(
            "SKU001", 10, "idempotency-key-1"
        )
        order = service.confirm_reservation(reservation.id)
        assert order.id is not None
        assert order.reservation_id == reservation.id
        assert order.quantity == 10

    def test_confirm_expired_reservation(self, service, repository):
        from datetime import datetime, timedelta
        from commerce_service.models import ReservationModel
        import uuid

        service.create_sku("SKU001", 100)

        session = repository.get_session()
        reservation_id = str(uuid.uuid4())
        reservation = ReservationModel(
            id=reservation_id,
            sku_id="SKU001",
            quantity=10,
            idempotency_key="expired-key",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        session.add(reservation)
        session.commit()
        session.close()

        with pytest.raises(InvalidReservationStateError, match="expired"):
            service.confirm_reservation(reservation_id)

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("nonexistent-id")

    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation(
            "SKU001", 10, "idempotency-key-1"
        )
        cancelled = service.cancel_reservation(reservation.id)
        assert cancelled.status.value == "cancelled"

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("nonexistent-id")

    def test_cancel_confirmed_reservation_fails(self, service):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation(
            "SKU001", 10, "idempotency-key-1"
        )
        service.confirm_reservation(reservation.id)
        with pytest.raises(InvalidReservationStateError):
            service.cancel_reservation(reservation.id)


class TestOrders:
    def test_list_orders_empty(self, service):
        orders, total = service.list_orders()
        assert orders == []
        assert total == 0

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU001", 1000)
        for i in range(25):
            res, _ = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(res.id)

        page1, total = service.list_orders(page=1, page_size=10)
        page2, _ = service.list_orders(page=2, page_size=10)
        page3, _ = service.list_orders(page=3, page_size=10)

        assert len(page1) == 10
        assert len(page2) == 10
        assert len(page3) == 5
        assert total == 25
