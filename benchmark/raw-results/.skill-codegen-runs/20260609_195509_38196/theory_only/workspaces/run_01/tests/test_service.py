import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InvalidStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    ReservationStatusError,
    IdempotencyError,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKU:
    def test_create_sku(self, service):
        sku = service.create_sku("SKU001", "Widget", 100.0)
        assert sku.id == "SKU001"
        assert sku.name == "Widget"
        assert sku.quantity_on_hand == 100.0

    def test_get_sku(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        sku = service.get_sku("SKU001")
        assert sku.id == "SKU001"

    def test_get_sku_not_found(self, service):
        with pytest.raises(ValueError, match="SKU missing_sku not found"):
            service.get_sku("missing_sku")

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        sku = service.adjust_stock("SKU001", 50.0)
        assert sku.quantity_on_hand == 150.0

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        sku = service.adjust_stock("SKU001", -30.0)
        assert sku.quantity_on_hand == 70.0

    def test_adjust_stock_below_zero_fails(self, service):
        service.create_sku("SKU001", "Widget", 50.0)
        with pytest.raises(InvalidStockError, match="Insufficient stock"):
            service.adjust_stock("SKU001", -100.0)

    def test_adjust_stock_sku_not_found(self, service):
        with pytest.raises(ValueError, match="SKU missing not found"):
            service.adjust_stock("missing", 10.0)


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        reservation = service.create_reservation("SKU001", 50.0)
        assert reservation.sku_id == "SKU001"
        assert reservation.quantity == 50.0
        assert reservation.status == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Widget", 50.0)
        with pytest.raises(InvalidStockError, match="Insufficient stock"):
            service.create_reservation("SKU001", 100.0)

    def test_create_reservation_accounts_for_pending_reservations(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        service.create_reservation("SKU001", 60.0)
        with pytest.raises(InvalidStockError, match="Insufficient stock"):
            service.create_reservation("SKU001", 50.0)

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(ValueError, match="SKU missing not found"):
            service.create_reservation("missing", 10.0)

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res1 = service.create_reservation("SKU001", 50.0, idempotency_key="key1")
        res2 = service.create_reservation("SKU001", 30.0, idempotency_key="key1")
        assert res1.id == res2.id
        assert res1.quantity == 50.0

    def test_create_reservation_canceled_idempotency_key_fails(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0, idempotency_key="key1")
        service.cancel_reservation(res.id)
        with pytest.raises(IdempotencyError, match="was used for a canceled reservation"):
            service.create_reservation("SKU001", 30.0, idempotency_key="key1")

    def test_get_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        fetched = service.get_reservation(res.id)
        assert fetched.id == res.id

    def test_get_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.get_reservation("missing")

    def test_cancel_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        canceled = service.cancel_reservation(res.id)
        assert canceled.status == ReservationStatus.CANCELED

    def test_cancel_reservation_already_confirmed_fails(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        service.confirm_reservation(res.id)
        with pytest.raises(ReservationStatusError, match="Cannot cancel reservation"):
            service.cancel_reservation(res.id)


class TestConfirmReservation:
    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        order = service.confirm_reservation(res.id)
        assert order.reservation_id == res.id
        assert order.sku_id == "SKU001"
        assert order.quantity == 50.0

    def test_confirm_reservation_idempotency(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        order1 = service.confirm_reservation(res.id, idempotency_key="confirm1")
        order2 = service.confirm_reservation(res.id, idempotency_key="confirm1")
        assert order1.id == order2.id

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("missing")

    def test_confirm_reservation_already_confirmed_fails(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        service.confirm_reservation(res.id)
        with pytest.raises(ReservationStatusError, match="Cannot confirm reservation"):
            service.confirm_reservation(res.id)

    def test_confirm_reservation_expired(self, service, db):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)

        # Manually expire the reservation
        res_entity = db.query(
            __import__("src.commerce_service.models", fromlist=["ReservationEntity"]).ReservationEntity
        ).filter_by(id=res.id).first()
        res_entity.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

        with pytest.raises(ReservationExpiredError, match="has expired"):
            service.confirm_reservation(res.id)

        # Verify status was updated to EXPIRED
        refreshed = service.get_reservation(res.id)
        assert refreshed.status == ReservationStatus.EXPIRED


class TestOrder:
    def test_get_order(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res = service.create_reservation("SKU001", 50.0)
        order = service.confirm_reservation(res.id)
        fetched = service.get_order(order.id)
        assert fetched.id == order.id

    def test_get_order_not_found(self, service):
        with pytest.raises(ValueError, match="Order missing not found"):
            service.get_order("missing")

    def test_list_orders(self, service):
        service.create_sku("SKU001", "Widget", 100.0)
        res1 = service.create_reservation("SKU001", 30.0)
        res2 = service.create_reservation("SKU001", 20.0)
        order1 = service.confirm_reservation(res1.id)
        order2 = service.confirm_reservation(res2.id)

        orders, total = service.list_orders(page=1, page_size=10)
        assert len(orders) == 2
        assert total == 2

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU001", "Widget", 1000.0)
        for i in range(25):
            res = service.create_reservation("SKU001", 10.0)
            service.confirm_reservation(res.id)

        orders1, total = service.list_orders(page=1, page_size=10)
        orders2, _ = service.list_orders(page=2, page_size=10)
        orders3, _ = service.list_orders(page=3, page_size=10)

        assert len(orders1) == 10
        assert len(orders2) == 10
        assert len(orders3) == 5
        assert total == 25
