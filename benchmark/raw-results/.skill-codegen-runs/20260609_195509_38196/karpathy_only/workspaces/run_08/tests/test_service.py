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
    ReservationNotFoundError,
    SKUNotFoundError,
    InvalidReservationStatusError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
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


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", "Test Product", 100)
        assert result["sku_id"] == "SKU001"
        assert result["name"] == "Test Product"
        assert result["available_stock"] == 100
        assert result["reserved_stock"] == 0

    def test_adjust_stock(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["available_stock"] == 150

        result = service.adjust_stock("SKU001", -30)
        assert result["available_stock"] == 120

    def test_adjust_stock_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservationCreation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        result = service.create_reservation("SKU001", "CUST001", 25)
        assert result["sku_id"] == "SKU001"
        assert result["customer_id"] == "CUST001"
        assert result["quantity"] == 25
        assert result["status"] == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Test Product", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", "CUST001", 100)

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", "CUST001", 10)

    def test_create_reservation_idempotent(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        key = "idempotency-key-1"
        result1 = service.create_reservation("SKU001", "CUST001", 25, idempotency_key=key)
        result2 = service.create_reservation("SKU001", "CUST001", 25, idempotency_key=key)
        assert result1["reservation_id"] == result2["reservation_id"]


class TestReservationConfirmation:
    def test_confirm_reservation(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)
        order = service.confirm_reservation(res["reservation_id"])
        assert order["order_id"]
        assert order["sku_id"] == "SKU001"
        assert order["quantity"] == 25

    def test_confirm_expired_reservation(self, service, repository):
        # Create SKU and reservation
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)

        # Manually expire the reservation
        reservation = repository.get_reservation(res["reservation_id"])
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        repository.db.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res["reservation_id"])

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_confirm_already_confirmed_reservation(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)
        service.confirm_reservation(res["reservation_id"])

        with pytest.raises(InvalidReservationStatusError):
            service.confirm_reservation(res["reservation_id"])


class TestReservationCancellation:
    def test_cancel_reservation(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)
        result = service.cancel_reservation(res["reservation_id"])
        assert result["status"] == ReservationStatus.CANCELLED

    def test_cancel_already_cancelled(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)
        service.cancel_reservation(res["reservation_id"])

        with pytest.raises(InvalidReservationStatusError):
            service.cancel_reservation(res["reservation_id"])

    def test_cancel_confirmed_reservation(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)
        service.confirm_reservation(res["reservation_id"])

        with pytest.raises(InvalidReservationStatusError):
            service.cancel_reservation(res["reservation_id"])


class TestOrderOperations:
    def test_get_order(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        res = service.create_reservation("SKU001", "CUST001", 25)
        order = service.confirm_reservation(res["reservation_id"])
        retrieved = service.get_order(order["order_id"])
        assert retrieved["order_id"] == order["order_id"]

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU001", "Test Product", 100)
        service.create_sku("SKU002", "Test Product 2", 100)

        # Create 5 orders
        for i in range(5):
            res = service.create_reservation(f"SKU00{1 + (i % 2)}", "CUST001", 10)
            service.confirm_reservation(res["reservation_id"])

        result = service.list_orders("CUST001", skip=0, limit=2)
        assert len(result["items"]) == 2
        assert result["total"] == 5
        assert result["skip"] == 0
        assert result["limit"] == 2

        result = service.list_orders("CUST001", skip=2, limit=2)
        assert len(result["items"]) == 2
