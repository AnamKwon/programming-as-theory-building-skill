import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import CommerceService, ConflictError, InsufficientStockError, InvalidStateError, NotFoundError


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
    repo = Repository(db_session)
    return CommerceService(repo)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", "Test SKU")
        assert result["sku_code"] == "SKU001"
        assert result["description"] == "Test SKU"
        assert result["created_at"] is not None

    def test_create_duplicate_sku_raises_conflict(self, service):
        service.create_sku("SKU001", "Test SKU")
        with pytest.raises(ConflictError):
            service.create_sku("SKU001", "Duplicate")

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU001", "Test")
        result = service.adjust_stock("SKU001", 100)
        assert result["quantity"] == 100
        assert result["reserved_quantity"] == 0

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["quantity"] == 70

    def test_adjust_stock_nonexistent_sku_raises_not_found(self, service):
        with pytest.raises(NotFoundError):
            service.adjust_stock("NONEXISTENT", 100)


class TestReservationOperations:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        result = service.create_reservation("SKU001", 10, "idempotency-1")
        assert result["reservation_id"] is not None
        assert result["sku_code"] == "SKU001"
        assert result["quantity"] == 10
        assert result["status"] == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 5)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 10, "idempotency-1")

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(NotFoundError):
            service.create_reservation("NONEXISTENT", 10, "idempotency-1")

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        result1 = service.create_reservation("SKU001", 10, "idempotency-1")
        result2 = service.create_reservation("SKU001", 10, "idempotency-1")
        assert result1["reservation_id"] == result2["reservation_id"]

    def test_create_reservation_idempotency_after_expiration(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        result1 = service.create_reservation("SKU001", 10, "idempotency-1")
        # Manually expire the reservation
        service.repo.update_reservation_status(result1["reservation_id"], ReservationStatus.EXPIRED)
        with pytest.raises(ConflictError):
            service.create_reservation("SKU001", 10, "idempotency-1")

    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        result = service.confirm_reservation(res["reservation_id"])
        assert result["status"] == ReservationStatus.CONFIRMED
        assert result["confirmed_at"] is not None

    def test_confirm_reservation_deducts_stock(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        stock_before = service.repo.get_stock("SKU001")
        service.confirm_reservation(res["reservation_id"])
        stock_after = service.repo.get_stock("SKU001")
        assert stock_after.quantity == 90
        assert stock_after.reserved_quantity == 0

    def test_confirm_expired_reservation_raises_error(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        # Manually expire it
        now = datetime.now(timezone.utc)
        service.repo.session.query(service.repo.session.query(Repository.__bases__[0]).get(res["reservation_id"]).__class__).filter_by(
            reservation_id=res["reservation_id"]
        ).update({"expires_at": now - timedelta(minutes=1)})
        service.repo.session.commit()
        with pytest.raises(InvalidStateError):
            service.confirm_reservation(res["reservation_id"])

    def test_cancel_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        result = service.cancel_reservation(res["reservation_id"])
        assert result["status"] == ReservationStatus.CANCELLED

    def test_cancel_reservation_releases_stock(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        stock_before = service.repo.get_stock("SKU001")
        assert stock_before.reserved_quantity == 10
        service.cancel_reservation(res["reservation_id"])
        stock_after = service.repo.get_stock("SKU001")
        assert stock_after.reserved_quantity == 0

    def test_cancel_confirmed_reservation_raises_error(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        service.confirm_reservation(res["reservation_id"])
        with pytest.raises(InvalidStateError):
            service.cancel_reservation(res["reservation_id"])


class TestOrderOperations:
    def test_get_order(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        confirmed = service.confirm_reservation(res["reservation_id"])
        # Get the order created by confirmation
        orders = service.repo.get_orders_paginated(1, 20)[0]
        assert len(orders) == 1
        order = orders[0]
        result = service.get_order(order.order_id)
        assert result["sku_code"] == "SKU001"
        assert result["quantity"] == 10

    def test_get_orders_pagination(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 200)
        for i in range(5):
            res = service.create_reservation("SKU001", 10, f"idempotency-{i}")
            service.confirm_reservation(res["reservation_id"])
        result = service.get_orders(page=1, page_size=2)
        assert result["total"] == 5
        assert len(result["orders"]) == 2
        assert result["page"] == 1
        assert result["page_size"] == 2


class TestExpirationManagement:
    def test_expire_pending_reservations(self, service):
        service.create_sku("SKU001", "Test")
        service.adjust_stock("SKU001", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1")
        # Manually expire it
        now = datetime.now(timezone.utc)
        reservation = service.repo.get_reservation(res["reservation_id"])
        reservation.expires_at = now - timedelta(minutes=1)
        service.repo.session.commit()
        count = service.expire_pending_reservations()
        assert count == 1
        updated = service.repo.get_reservation(res["reservation_id"])
        assert updated.status == ReservationStatus.EXPIRED
