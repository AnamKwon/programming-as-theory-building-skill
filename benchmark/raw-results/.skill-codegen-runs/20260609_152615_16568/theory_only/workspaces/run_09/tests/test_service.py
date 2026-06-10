"""Unit tests for business logic layer."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    ExpiredReservationError,
    InsufficientStockError,
    InvalidStateError,
    Service,
    ServiceError,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create a service instance with test database."""
    return Service(Repository(db_session))


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        assert result["id"] == "SHOE-001"
        assert result["name"] == "Running Shoes"

    def test_create_duplicate_sku_raises_error(self, service):
        service.create_sku("SHOE-001", "Running Shoes")
        with pytest.raises(ServiceError):
            service.create_sku("SHOE-001", "Another Shoe")

    def test_get_sku(self, service):
        service.create_sku("SHOE-001", "Running Shoes")
        result = service.get_sku("SHOE-001")
        assert result["name"] == "Running Shoes"

    def test_get_nonexistent_sku_returns_none(self, service):
        result = service.get_sku("NONEXISTENT")
        assert result is None


class TestStockManagement:
    def test_adjust_stock_increase(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        result = service.adjust_stock("SHOE-001", 10)
        assert result["available"] == 60
        assert result["reserved"] == 0

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        result = service.adjust_stock("SHOE-001", -10)
        assert result["available"] == 40

    def test_adjust_stock_nonexistent_raises_error(self, service):
        with pytest.raises(ServiceError):
            service.adjust_stock("NONEXISTENT", 10)

    def test_get_stock(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        result = service.get_stock("SHOE-001")
        assert result["available"] == 50
        assert result["reserved"] == 0


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        result = service.create_reservation("SHOE-001", 5)
        assert result["quantity"] == 5
        assert result["status"] == "reserved"

    def test_create_reservation_decrements_available(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        service.create_reservation("SHOE-001", 5)
        stock = service.get_stock("SHOE-001")
        assert stock["available"] == 45
        assert stock["reserved"] == 5

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=3)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SHOE-001", 5)

    def test_create_reservation_with_idempotency_key(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        result1 = service.create_reservation("SHOE-001", 5, idempotency_key="key-123")
        result2 = service.create_reservation("SHOE-001", 5, idempotency_key="key-123")
        assert result1["id"] == result2["id"]

    def test_create_reservation_idempotency_prevents_double_reserve(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        service.create_reservation("SHOE-001", 5, idempotency_key="key-123")
        service.create_reservation("SHOE-001", 5, idempotency_key="key-123")
        stock = service.get_stock("SHOE-001")
        assert stock["reserved"] == 5

    def test_cancel_reservation_releases_stock(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        res = service.create_reservation("SHOE-001", 5)
        service.cancel_reservation(res["id"])
        stock = service.get_stock("SHOE-001")
        assert stock["available"] == 50
        assert stock["reserved"] == 0

    def test_cancel_nonexistent_reservation_raises_error(self, service):
        with pytest.raises(Exception):  # NotFoundError
            service.cancel_reservation("nonexistent-id")


class TestReservationExpiration:
    def test_confirm_expired_reservation_raises_error(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        res = service.create_reservation("SHOE-001", 5)

        repo = service.repo
        reservation = repo.get_reservation(res["id"])
        reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        repo.session.flush()
        repo.commit()

        with pytest.raises(ExpiredReservationError):
            service.confirm_reservation(res["id"])

    def test_expired_reservation_returns_stock(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        res = service.create_reservation("SHOE-001", 5)

        repo = service.repo
        reservation = repo.get_reservation(res["id"])
        reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        repo.session.flush()
        repo.commit()

        with pytest.raises(ExpiredReservationError):
            service.confirm_reservation(res["id"])

        stock = service.get_stock("SHOE-001")
        assert stock["available"] == 50


class TestOrderConfirmation:
    def test_confirm_reservation_creates_order(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        res = service.create_reservation("SHOE-001", 5)
        order = service.confirm_reservation(res["id"])
        assert order["status"] == "confirmed"
        assert order["reservation_id"] == res["id"]

    def test_confirm_removes_reserved_stock(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        res = service.create_reservation("SHOE-001", 5)
        service.confirm_reservation(res["id"])
        stock = service.get_stock("SHOE-001")
        assert stock["available"] == 45
        assert stock["reserved"] == 0

    def test_confirm_nonconfirmable_state_raises_error(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        res = service.create_reservation("SHOE-001", 5)
        service.cancel_reservation(res["id"])
        with pytest.raises(InvalidStateError):
            service.confirm_reservation(res["id"])


class TestOrderListing:
    def test_list_orders_pagination(self, service):
        service.create_sku("SHOE-001", "Running Shoes", initial_stock=50)
        for i in range(15):
            res = service.create_reservation("SHOE-001", 1)
            service.confirm_reservation(res["id"])

        page1 = service.list_orders(page=1, page_size=10)
        assert len(page1["orders"]) == 10
        assert page1["total"] == 15
        assert page1["pages"] == 2

        page2 = service.list_orders(page=2, page_size=10)
        assert len(page2["orders"]) == 5

    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["orders"] == []
        assert result["total"] == 0
