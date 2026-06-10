import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.commerce_service.models import Base, OrderStatus, ReservationStatus
from src.commerce_service.service import (
    CommerceService,
    DuplicateReservationError,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
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


class TestSKUManagement:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU-001", "Test Product", 100)
        assert sku.code == "SKU-001"
        assert sku.name == "Test Product"
        assert sku.available_stock == 100

    def test_adjust_stock_positive(self, service):
        sku = service.create_sku("SKU-001", "Product", 50)
        adjusted = service.adjust_stock(sku.id, 30)
        assert adjusted.available_stock == 80

    def test_adjust_stock_negative(self, service):
        sku = service.create_sku("SKU-001", "Product", 50)
        adjusted = service.adjust_stock(sku.id, -20)
        assert adjusted.available_stock == 30

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError):
            service.adjust_stock(999, 10)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "idempotency-key-1")

        reservation = result["reservation"]
        assert reservation.sku_id == sku.id
        assert reservation.amount == 50
        assert reservation.status == ReservationStatus.PENDING
        assert reservation.idempotency_key == "idempotency-key-1"
        assert not result["is_duplicate"]

    def test_create_reservation_insufficient_stock(self, service):
        sku = service.create_sku("SKU-001", "Product", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(sku.id, 100, "key-1")

    def test_create_reservation_idempotent_retry(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result1 = service.create_reservation(sku.id, 50, "idempotency-key-1")
        result2 = service.create_reservation(sku.id, 50, "idempotency-key-1")

        assert result1["reservation"].id == result2["reservation"].id
        assert result2["is_duplicate"] is True

    def test_create_reservation_expired_idempotency_rejected(self, service, db):
        sku = service.create_sku("SKU-001", "Product", 100)
        result1 = service.create_reservation(sku.id, 50, "key-1")

        reservation = result1["reservation"]
        reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
        reservation.status = ReservationStatus.EXPIRED
        db.commit()

        with pytest.raises(DuplicateReservationError):
            service.create_reservation(sku.id, 50, "key-1")

    def test_confirm_reservation_happy_path(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "key-1")
        reservation_id = result["reservation"].id

        confirmed = service.confirm_reservation(reservation_id)
        assert confirmed["reservation"].status == ReservationStatus.CONFIRMED
        assert confirmed["reservation"].id == reservation_id

        sku_after = service.sku_repo.get_by_id(sku.id)
        assert sku_after.available_stock == 50

    def test_confirm_reservation_expired(self, service, db):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "key-1")
        reservation_id = result["reservation"].id

        reservation = service.reservation_repo.get_by_id(reservation_id)
        reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation_id)

    def test_confirm_already_confirmed_reservation(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "key-1")
        reservation_id = result["reservation"].id

        service.confirm_reservation(reservation_id)

        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(reservation_id)

    def test_cancel_reservation(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "key-1")
        reservation_id = result["reservation"].id

        cancelled = service.cancel_reservation(reservation_id)
        assert cancelled["reservation"].status == ReservationStatus.CANCELLED

    def test_cancel_confirmed_reservation_refunds_stock(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "key-1")
        reservation_id = result["reservation"].id

        service.confirm_reservation(reservation_id)
        sku_after_confirm = service.sku_repo.get_by_id(sku.id)
        assert sku_after_confirm.available_stock == 50

        service.cancel_reservation(reservation_id)
        sku_after_cancel = service.sku_repo.get_by_id(sku.id)
        assert sku_after_cancel.available_stock == 100

    def test_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)


class TestOrders:
    def test_create_order_via_reservation(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation(sku.id, 50, "key-1")
        order_id = result["order_id"]

        order = service.get_order(order_id)
        assert order.sku_id == sku.id
        assert order.amount == 50
        assert order.status == OrderStatus.PENDING

    def test_list_orders_pagination(self, service):
        sku = service.create_sku("SKU-001", "Product", 100)

        for i in range(15):
            service.create_reservation(sku.id, 10, f"key-{i}")

        page1 = service.list_orders(1, 10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 15
        assert page1["total_pages"] == 2
        assert page1["page"] == 1

        page2 = service.list_orders(2, 10)
        assert len(page2["items"]) == 5
        assert page2["page"] == 2
