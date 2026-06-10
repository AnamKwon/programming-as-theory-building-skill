import os
import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    _, db_path = tempfile.mkstemp(suffix=".db")
    yield f"sqlite:///{db_path}"
    os.unlink(db_path)


@pytest.fixture
def service(temp_db):
    repo = Repository(database_url=temp_db)
    return CommerceService(repo)


class TestSKU:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU-001", "Widget", "A useful widget")
        assert sku.id == "SKU-001"
        assert sku.name == "Widget"
        assert sku.description == "A useful widget"

    def test_create_duplicate_sku_raises(self, service):
        service.create_sku("SKU-001", "Widget")
        with pytest.raises(ValueError, match="already exists"):
            service.create_sku("SKU-001", "Another")

    def test_get_sku(self, service):
        service.create_sku("SKU-001", "Widget")
        sku = service.get_sku("SKU-001")
        assert sku.id == "SKU-001"

    def test_get_nonexistent_sku_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.get_sku("NONEXISTENT")


class TestStock:
    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU-001", "Widget")
        stock = service.adjust_stock("SKU-001", 100)
        assert stock.quantity_available == 100
        assert stock.quantity_reserved == 0

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        stock = service.adjust_stock("SKU-001", -30)
        assert stock.quantity_available == 70

    def test_adjust_stock_below_zero_raises(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 10)
        with pytest.raises(ValueError, match="cannot be negative"):
            service.adjust_stock("SKU-001", -20)

    def test_adjust_stock_nonexistent_sku_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservation:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        assert reservation.sku_id == "SKU-001"
        assert reservation.quantity == 10
        assert reservation.status == ReservationStatus.PENDING
        assert reservation.expires_at > datetime.utcnow()

    def test_create_reservation_insufficient_stock_raises(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 5)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU-001", 10)

    def test_create_reservation_idempotent(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)

        key = "idempotency-key-1"
        res1 = service.create_reservation("SKU-001", 10, idempotency_key=key)
        res2 = service.create_reservation("SKU-001", 10, idempotency_key=key)

        assert res1.id == res2.id

    def test_create_reservation_nonexistent_sku_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.create_reservation("NONEXISTENT", 10)

    def test_get_expired_reservation_marks_expired(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        session = service.repo.SessionLocal()
        try:
            from commerce_service.models import ReservationModel
            session.query(ReservationModel).filter_by(id=reservation.id).update(
                {"expires_at": datetime.utcnow() - timedelta(minutes=1)}
            )
            session.commit()
        finally:
            session.close()

        fetched = service.get_reservation(reservation.id)
        assert fetched.status == ReservationStatus.EXPIRED

    def test_cancel_pending_reservation_releases_stock(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        service.cancel_reservation(reservation.id)

        stock = service.repo.get_stock("SKU-001")
        assert stock.quantity_available == 100
        assert stock.quantity_reserved == 0


class TestOrder:
    def test_confirm_reservation_creates_order(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        order = service.confirm_reservation(reservation.id)

        assert order.reservation_id == reservation.id
        assert order.status == OrderStatus.CONFIRMED

    def test_confirm_reservation_idempotent(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        order1 = service.confirm_reservation(reservation.id, idempotency_key="order-key-1")
        order2 = service.confirm_reservation(reservation.id, idempotency_key="order-key-1")

        assert order1.id == order2.id

    def test_confirm_expired_reservation_raises(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        session = service.repo.SessionLocal()
        try:
            from commerce_service.models import ReservationModel
            session.query(ReservationModel).filter_by(id=reservation.id).update(
                {"expires_at": datetime.utcnow() - timedelta(minutes=1)}
            )
            session.commit()
        finally:
            session.close()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(reservation.id)

    def test_confirm_nonpending_reservation_raises(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)

        service.confirm_reservation(reservation.id)

        with pytest.raises(ValueError, match="Cannot confirm"):
            service.confirm_reservation(reservation.id)

    def test_get_order(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 10)
        order = service.confirm_reservation(reservation.id)

        fetched = service.get_order(order.id)
        assert fetched.id == order.id

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU-001", "Widget")
        service.adjust_stock("SKU-001", 100)

        for i in range(15):
            res = service.create_reservation("SKU-001", 1)
            service.confirm_reservation(res.id)

        orders, total = service.list_orders(skip=0, limit=10)
        assert len(orders) == 10
        assert total == 15

        orders, total = service.list_orders(skip=10, limit=10)
        assert len(orders) == 5
        assert total == 15
