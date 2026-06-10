import pytest
from datetime import datetime, timedelta

from commerce_service.models import ReservationState
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)


@pytest.fixture
def repository():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repository):
    return CommerceService(repository)


class TestSKUManagement:
    def test_create_sku(self, service):
        response = service.create_sku("SKU-001", "Widget", 100)
        assert response.id == "SKU-001"
        assert response.name == "Widget"
        assert response.available_stock == 100
        assert response.reserved_stock == 0

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU-001", "Widget", 10)
        response = service.adjust_stock("SKU-001", 5)
        assert response.available_stock == 15

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU-001", "Widget", 10)
        response = service.adjust_stock("SKU-001", -3)
        assert response.available_stock == 7

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="SKU .* not found"):
            service.adjust_stock("NONEXISTENT", 5)


class TestReservation:
    def test_reserve_happy_path(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        response = service.reserve("SKU-001", 10)

        assert response.sku_id == "SKU-001"
        assert response.quantity == 10
        assert response.state == ReservationState.RESERVED
        assert response.expires_at is not None

        sku = service.repo.get_sku("SKU-001")
        assert sku.available_stock == 90
        assert sku.reserved_stock == 10

    def test_reserve_insufficient_stock(self, service):
        service.create_sku("SKU-001", "Widget", 10)
        with pytest.raises(InsufficientStockError):
            service.reserve("SKU-001", 20)

    def test_reserve_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="SKU .* not found"):
            service.reserve("NONEXISTENT", 5)

    def test_reserve_with_idempotency_key(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        idempotency_key = "idempotency-001"

        response1 = service.reserve("SKU-001", 10, idempotency_key)
        response2 = service.reserve("SKU-001", 10, idempotency_key)

        assert response1.id == response2.id
        sku = service.repo.get_sku("SKU-001")
        assert sku.reserved_stock == 10

    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        reservation = service.reserve("SKU-001", 10)

        response = service.confirm_reservation(reservation.id)

        assert response.state == ReservationState.CONFIRMED
        assert response.confirmed_at is not None

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_confirm_already_confirmed(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        reservation = service.reserve("SKU-001", 10)
        service.confirm_reservation(reservation.id)

        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(reservation.id)

    def test_confirm_expired_reservation(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        reservation = service.repo.create_reservation(
            "RES-001",
            "SKU-001",
            10,
            datetime.utcnow() - timedelta(minutes=1),
        )

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation("RES-001")

    def test_cancel_reserved_reservation(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        reservation = service.reserve("SKU-001", 10)

        response = service.cancel_reservation(reservation.id)

        assert response.state == ReservationState.CANCELLED
        sku = service.repo.get_sku("SKU-001")
        assert sku.available_stock == 100
        assert sku.reserved_stock == 0

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")

    def test_cancel_already_confirmed(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        reservation = service.reserve("SKU-001", 10)
        service.confirm_reservation(reservation.id)

        with pytest.raises(InvalidStateTransitionError):
            service.cancel_reservation(reservation.id)

    def test_cancel_already_cancelled(self, service):
        service.create_sku("SKU-001", "Widget", 100)
        reservation = service.reserve("SKU-001", 10)
        service.cancel_reservation(reservation.id)

        response = service.cancel_reservation(reservation.id)
        assert response.state == ReservationState.CANCELLED

    def test_cleanup_expired_reservations(self, service):
        service.create_sku("SKU-001", "Widget", 100)

        service.repo.create_reservation(
            "RES-001",
            "SKU-001",
            10,
            datetime.utcnow() - timedelta(minutes=1),
        )
        service.repo.update_sku_stock("SKU-001", -10, 10)

        service.repo.create_reservation(
            "RES-002",
            "SKU-001",
            20,
            datetime.utcnow() + timedelta(minutes=10),
        )
        service.repo.update_sku_stock("SKU-001", -20, 20)

        count = service.cleanup_expired_reservations()

        assert count == 1
        sku = service.repo.get_sku("SKU-001")
        assert sku.available_stock == 90
        assert sku.reserved_stock == 20
