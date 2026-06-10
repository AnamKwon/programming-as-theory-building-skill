import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, ReservationRequest, ReservationState
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
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
def service(db_session):
    repo = Repository(db_session)
    return CommerceService(repo)


class TestReservation:
    def test_reserve_happy_path(self, service):
        """Test successful reservation creation."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        reservation = service.reserve(request)

        assert reservation.id is not None
        assert reservation.state == ReservationState.PENDING
        assert reservation.quantity == 10
        assert reservation.sku_id == "sku-1"

    def test_reserve_insufficient_stock(self, service):
        """Test reservation fails when stock is insufficient."""
        service.create_sku("sku-1", "Widget", 5)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")

        with pytest.raises(InsufficientStockError):
            service.reserve(request)

    def test_reserve_idempotent_retry(self, service):
        """Test that retrying with same idempotency key returns existing reservation."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")

        res1 = service.reserve(request)
        res2 = service.reserve(request)

        assert res1.id == res2.id
        assert res1.created_at == res2.created_at

    def test_reserve_sku_not_found(self, service):
        """Test reservation fails when SKU doesn't exist."""
        request = ReservationRequest(sku_id="sku-missing", quantity=10, idempotency_key="key-1")

        with pytest.raises(SKUNotFoundError):
            service.reserve(request)

    def test_confirm_reservation_happy_path(self, service):
        """Test successful reservation confirmation."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        reservation = service.reserve(request)

        confirmed = service.confirm_reservation(reservation.id)

        assert confirmed.state == ReservationState.CONFIRMED

    def test_confirm_expired_reservation(self, service):
        """Test that confirming an expired reservation fails."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        reservation = service.reserve(request)

        # Manually expire the reservation
        service.repo.session.query(type(reservation)).filter(
            type(reservation).id == reservation.id
        ).update({"expires_at": datetime.utcnow() - timedelta(minutes=1)})
        service.repo.session.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(reservation.id)

    def test_cancel_reservation(self, service):
        """Test successful reservation cancellation."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        reservation = service.reserve(request)

        cancelled = service.cancel_reservation(reservation.id)

        assert cancelled.state == ReservationState.CANCELLED

    def test_cancel_nonexistent_reservation(self, service):
        """Test cancelling nonexistent reservation fails."""
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("res-missing")


class TestStock:
    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        sku = service.create_sku("sku-1", "Widget", 100)
        adjusted = service.adjust_stock("sku-1", 50)

        assert adjusted.available_stock == 150

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku("sku-1", "Widget", 100)
        adjusted = service.adjust_stock("sku-1", -30)

        assert adjusted.available_stock == 70

    def test_adjust_stock_sku_not_found(self, service):
        """Test adjusting stock for missing SKU fails."""
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("sku-missing", 10)

    def test_stock_reserved_after_reservation(self, service):
        """Test that stock is reserved when reservation is created."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        service.reserve(request)

        sku = service.repo.get_sku("sku-1")
        assert sku.available_stock == 100
        assert sku.reserved_stock == 10

    def test_stock_returned_after_cancellation(self, service):
        """Test that reserved stock is returned when reservation is cancelled."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        reservation = service.reserve(request)
        service.cancel_reservation(reservation.id)

        sku = service.repo.get_sku("sku-1")
        assert sku.reserved_stock == 0


class TestCleanup:
    def test_cleanup_expired_reservations(self, service):
        """Test that cleanup marks expired reservations."""
        service.create_sku("sku-1", "Widget", 100)
        request = ReservationRequest(sku_id="sku-1", quantity=10, idempotency_key="key-1")
        reservation = service.reserve(request)

        # Manually expire the reservation
        service.repo.session.query(type(reservation)).filter(
            type(reservation).id == reservation.id
        ).update({"expires_at": datetime.utcnow() - timedelta(minutes=1)})
        service.repo.session.commit()

        expired = service.cleanup_expired_reservations()

        assert len(expired) == 1
        assert expired[0].id == reservation.id
        assert expired[0].state == ReservationState.EXPIRED
