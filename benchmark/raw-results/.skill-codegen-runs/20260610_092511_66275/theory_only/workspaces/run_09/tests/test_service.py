import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidReservationStateError,
)


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return Service(repo)


class TestSkuOperations:
    def test_create_sku(self, service):
        result = service.create_sku("Widget A", 100)
        assert result["name"] == "Widget A"
        assert result["total_stock"] == 100
        assert result["reserved_stock"] == 0

    def test_adjust_stock_increase(self, service):
        service.create_sku("Widget A", 100)
        result = service.adjust_stock(1, 50)
        assert result["total_stock"] == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("Widget A", 100)
        result = service.adjust_stock(1, -30)
        assert result["total_stock"] == 70

    def test_adjust_stock_not_found(self, service):
        with pytest.raises(Exception):
            service.adjust_stock(999, 10)


class TestReservationHappyPath:
    def test_create_reservation_success(self, service):
        service.create_sku("Widget A", 100)
        result = service.create_reservation(1, 50, "order-123")
        assert result["status"].value == "pending"
        assert result["quantity"] == 50
        assert result["sku_id"] == 1

    def test_confirm_reservation(self, service):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 50, "order-123")
        result = service.confirm_reservation(1)
        assert result["status"].value == "confirmed"
        assert "order_id" in result

    def test_cancel_reservation(self, service):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 50, "order-123")
        result = service.cancel_reservation(1)
        assert result["status"].value == "cancelled"


class TestInsufficientStock:
    def test_insufficient_stock_error(self, service):
        service.create_sku("Widget A", 100)
        with pytest.raises(InsufficientStockError):
            service.create_reservation(1, 150, "order-123")

    def test_multiple_reservations_exhausts_stock(self, service):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 60, "order-1")
        with pytest.raises(InsufficientStockError):
            service.create_reservation(1, 50, "order-2")


class TestIdempotency:
    def test_idempotent_reservation_retry(self, service):
        service.create_sku("Widget A", 100)
        result1 = service.create_reservation(1, 50, "order-123")
        result2 = service.create_reservation(1, 50, "order-123")
        assert result1["id"] == result2["id"]
        assert result1["status"] == result2["status"]

    def test_stock_not_double_reserved_on_idempotent_retry(self, service):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 50, "order-123")
        service.create_reservation(1, 50, "order-123")

        sku = service.repo.get_sku(1)
        assert sku.reserved_stock == 50


class TestReservationExpiration:
    def test_cannot_confirm_expired_reservation(self, service, repo):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 50, "order-123")

        reservation = repo.get_reservation(1)
        reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
        session = repo.get_session()
        session.merge(reservation)
        session.commit()
        session.close()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(1)


class TestReservationStateTransitions:
    def test_cannot_cancel_confirmed_reservation(self, service):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 50, "order-123")
        service.confirm_reservation(1)

        with pytest.raises(InvalidReservationStateError):
            service.cancel_reservation(1)

    def test_cannot_confirm_twice(self, service):
        service.create_sku("Widget A", 100)
        service.create_reservation(1, 50, "order-123")
        service.confirm_reservation(1)

        with pytest.raises(InvalidReservationStateError):
            service.confirm_reservation(1)

    def test_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)


class TestOrderLookup:
    def test_get_orders_empty(self, service):
        result = service.get_orders()
        assert result["total"] == 0
        assert result["orders"] == []

    def test_get_orders_with_pagination(self, service):
        service.create_sku("Widget A", 100)
        for i in range(5):
            service.create_reservation(1, 10, f"order-{i}")
            service.confirm_reservation(i + 1)

        result = service.get_orders(limit=2, offset=0)
        assert len(result["orders"]) == 2
        assert result["total"] == 5
        assert result["limit"] == 2
        assert result["offset"] == 0
