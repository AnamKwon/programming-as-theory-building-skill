import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from commerce_service.models import Base, ReservationStatus, OrderStatus
from commerce_service.service import CommerceService, RESERVATION_TTL_MINUTES


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


class TestSKUManagement:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU-001", 100)
        assert sku.code == "SKU-001"
        assert sku.stock == 100
        assert sku.reserved_count == 0

    def test_create_duplicate_sku_raises_conflict(self, service):
        service.create_sku("SKU-001", 100)
        with pytest.raises(HTTPException) as exc_info:
            service.create_sku("SKU-001", 50)
        assert "already exists" in exc_info.value.detail

    def test_adjust_stock(self, service):
        sku = service.create_sku("SKU-001", 100)
        adjusted = service.adjust_stock(sku.id, 50)
        assert adjusted.stock == 150

    def test_adjust_stock_negative(self, service):
        sku = service.create_sku("SKU-001", 100)
        adjusted = service.adjust_stock(sku.id, -30)
        assert adjusted.stock == 70


class TestReservation:
    def test_reserve_happy_path(self, service):
        sku = service.create_sku("SKU-001", 100)
        reservation = service.reserve(sku.id, 10, "idempotency-1")
        assert reservation.quantity == 10
        assert reservation.status == ReservationStatus.PENDING
        assert sku.reserved_count == 10

    def test_reserve_idempotent(self, service):
        sku = service.create_sku("SKU-001", 100)
        res1 = service.reserve(sku.id, 10, "idempotency-1")
        res2 = service.reserve(sku.id, 10, "idempotency-1")
        assert res1.id == res2.id

    def test_reserve_insufficient_stock(self, service):
        sku = service.create_sku("SKU-001", 100)
        service.reserve(sku.id, 95, "idempotency-1")
        with pytest.raises(HTTPException) as exc_info:
            service.reserve(sku.id, 10, "idempotency-2")
        assert "Insufficient stock" in exc_info.value.detail

    def test_reserve_nonexistent_sku(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.reserve(999, 10, "idempotency-1")
        assert "not found" in exc_info.value.detail

    def test_confirm_reservation(self, service):
        sku = service.create_sku("SKU-001", 100)
        reservation = service.reserve(sku.id, 10, "idempotency-1")
        order = service.confirm_reservation(reservation.id)
        assert order.reservation_id == reservation.id
        assert order.status == OrderStatus.RESERVED

    def test_confirm_idempotent(self, service):
        sku = service.create_sku("SKU-001", 100)
        reservation = service.reserve(sku.id, 10, "idempotency-1")
        order1 = service.confirm_reservation(reservation.id)
        order2 = service.confirm_reservation(reservation.id)
        assert order1.id == order2.id

    def test_cancel_reservation(self, service):
        sku = service.create_sku("SKU-001", 100)
        reservation = service.reserve(sku.id, 10, "idempotency-1")
        assert sku.reserved_count == 10
        cancelled = service.cancel_reservation(reservation.id)
        assert cancelled.status == ReservationStatus.CANCELLED
        assert sku.reserved_count == 0

    def test_cancel_already_confirmed_fails(self, service):
        sku = service.create_sku("SKU-001", 100)
        reservation = service.reserve(sku.id, 10, "idempotency-1")
        service.confirm_reservation(reservation.id)
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(reservation.id)
        assert "Cannot cancel" in exc_info.value.detail


class TestReservationExpiry:
    def test_expired_reservation_cannot_be_confirmed(self, db, service):
        from commerce_service.repository import ReservationRepository

        sku = service.create_sku("SKU-001", 100)
        reservation = service.reserve(sku.id, 10, "idempotency-1")

        repo = ReservationRepository(db)
        past = datetime.utcnow() - timedelta(minutes=1)
        reservation.expires_at = past
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(reservation.id)
        assert "expired" in exc_info.value.detail.lower()

    def test_expire_stale_releases_stock(self, db, service):
        from commerce_service.repository import ReservationRepository

        sku = service.create_sku("SKU-001", 100)
        res1 = service.reserve(sku.id, 10, "idempotency-1")
        res2 = service.reserve(sku.id, 5, "idempotency-2")

        assert sku.reserved_count == 15

        repo = ReservationRepository(db)
        past = datetime.utcnow() - timedelta(minutes=1)
        res1.expires_at = past
        db.commit()

        repo.expire_stale()

        refreshed = service.sku_repo.get_by_id(sku.id)
        assert refreshed.reserved_count == 5
        assert res1.status == ReservationStatus.EXPIRED
        assert res2.status == ReservationStatus.PENDING


class TestOrderLookup:
    def test_list_orders_empty(self, service):
        orders, total = service.list_orders()
        assert total == 0
        assert len(orders) == 0

    def test_list_orders_pagination(self, service):
        sku = service.create_sku("SKU-001", 1000)

        for i in range(25):
            res = service.reserve(sku.id, 1, f"idempotency-{i}")
            service.confirm_reservation(res.id)

        orders, total = service.list_orders(skip=0, limit=10)
        assert total == 25
        assert len(orders) == 10

        orders2, _ = service.list_orders(skip=10, limit=10)
        assert len(orders2) == 10

        orders3, _ = service.list_orders(skip=20, limit=10)
        assert len(orders3) == 5
