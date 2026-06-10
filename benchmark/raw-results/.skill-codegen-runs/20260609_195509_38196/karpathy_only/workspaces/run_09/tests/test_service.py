import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
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
def repository(db_session):
    return Repository(db_session)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SKU-001", 100)
        assert result["sku_id"] == "SKU-001"
        assert result["available_stock"] == 100

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU-002", 50)
        result = service.adjust_stock("SKU-002", 25)
        assert result["available_stock"] == 75

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU-003", 50)
        result = service.adjust_stock("SKU-003", -10)
        assert result["available_stock"] == 40

    def test_adjust_stock_nonexistent(self, service):
        with pytest.raises(ValueError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU-004", 100)
        result = service.create_reservation("SKU-004", 50)
        assert result["sku_id"] == "SKU-004"
        assert result["quantity"] == 50
        assert result["status"] == "pending"
        assert result["expires_at"] > datetime.utcnow()

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-005", 30)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU-005", 50)

    def test_create_reservation_with_pending(self, service):
        service.create_sku("SKU-006", 100)
        service.create_reservation("SKU-006", 60)
        # Only 40 left available
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU-006", 50)

    def test_create_reservation_with_idempotency(self, service):
        service.create_sku("SKU-007", 100)
        result1 = service.create_reservation("SKU-007", 30, "key-1")
        result2 = service.create_reservation("SKU-007", 30, "key-1")
        assert result1["reservation_id"] == result2["reservation_id"]


class TestReservationConfirmation:
    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU-008", 100)
        res = service.create_reservation("SKU-008", 40)
        order = service.confirm_reservation(res["reservation_id"])
        assert order["sku_id"] == "SKU-008"
        assert order["quantity"] == 40
        assert "order_id" in order

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_confirm_expired_reservation(self, service, repository):
        service.create_sku("SKU-009", 100)
        res = service.create_reservation("SKU-009", 50)
        # Manually expire the reservation
        reservation = repository.get_reservation(res["reservation_id"])
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        repository.session.commit()
        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res["reservation_id"])


class TestReservationCancellation:
    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU-010", 100)
        res = service.create_reservation("SKU-010", 30)
        result = service.cancel_reservation(res["reservation_id"])
        assert result["status"] == "cancelled"

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")


class TestOrderLookup:
    def test_get_orders_empty(self, service):
        result = service.get_orders()
        assert result["orders"] == []
        assert result["total"] == 0

    def test_get_orders_pagination(self, service):
        service.create_sku("SKU-011", 500)
        for i in range(25):
            res = service.create_reservation("SKU-011", 1)
            service.confirm_reservation(res["reservation_id"])

        result1 = service.get_orders(page=1, page_size=10)
        assert len(result1["orders"]) == 10
        assert result1["page"] == 1
        assert result1["total"] == 25

        result2 = service.get_orders(page=2, page_size=10)
        assert len(result2["orders"]) == 10
        assert result2["page"] == 2
