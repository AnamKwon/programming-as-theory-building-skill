import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import (
    Base,
    ReservationStatus,
    OrderStatus,
)
from commerce_service.service import (
    CommercService,
    SKUAlreadyExistsError,
    SKUNotFoundError,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    """Create service instance with test database."""
    return CommercService(db)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("WIDGET-001", "Widget A", 100)
        assert result["sku"] == "WIDGET-001"
        assert result["name"] == "Widget A"
        assert result["stock"] == 100
        assert result["reserved"] == 0

    def test_create_sku_duplicate(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        with pytest.raises(SKUAlreadyExistsError):
            service.create_sku("WIDGET-001", "Widget A", 50)

    def test_get_sku(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        result = service.get_sku("WIDGET-001")
        assert result["sku"] == "WIDGET-001"
        assert result["stock"] == 100
        assert result["reserved"] == 0

    def test_get_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.get_sku("NONEXISTENT")

    def test_adjust_stock_increase(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        result = service.adjust_stock("WIDGET-001", 50)
        assert result["stock"] == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        result = service.adjust_stock("WIDGET-001", -30)
        assert result["stock"] == 70

    def test_adjust_stock_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        result = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        assert result["sku"] == "WIDGET-001"
        assert result["quantity"] == 10
        assert result["status"] == ReservationStatus.PENDING
        assert result["reservation_id"] is not None

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("WIDGET-001", 150, "idem-key-1")

    def test_create_reservation_idempotent(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        result1 = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        result2 = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        assert result1["reservation_id"] == result2["reservation_id"]

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", 10, "idem-key-1")

    def test_confirm_reservation(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        res = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        confirmed = service.confirm_reservation(res["reservation_id"])
        assert confirmed["status"] == ReservationStatus.CONFIRMED

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_reservation_invalid_state(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        res = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        service.confirm_reservation(res["reservation_id"])
        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(res["reservation_id"])

    def test_cancel_reservation(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        res = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        cancelled = service.cancel_reservation(res["reservation_id"])
        assert cancelled["status"] == ReservationStatus.CANCELLED

    def test_cancel_reservation_confirmed(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        res = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        service.confirm_reservation(res["reservation_id"])
        cancelled = service.cancel_reservation(res["reservation_id"])
        assert cancelled["status"] == ReservationStatus.CANCELLED

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)


class TestStockAvailability:
    def test_available_stock_with_pending_reservation(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        service.create_reservation("WIDGET-001", 30, "idem-1")
        sku = service.get_sku("WIDGET-001")
        assert sku["reserved"] == 30
        assert sku["stock"] == 100

    def test_available_stock_with_confirmed_reservation(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        res = service.create_reservation("WIDGET-001", 30, "idem-1")
        service.confirm_reservation(res["reservation_id"])
        sku = service.get_sku("WIDGET-001")
        assert sku["reserved"] == 30

    def test_cannot_exceed_available_stock(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        service.create_reservation("WIDGET-001", 60, "idem-1")
        with pytest.raises(InsufficientStockError):
            service.create_reservation("WIDGET-001", 50, "idem-2")


class TestOrderCreation:
    def test_order_created_on_confirm(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        res = service.create_reservation("WIDGET-001", 10, "idem-key-1")
        service.confirm_reservation(res["reservation_id"])
        orders, _ = service.order_repo.list_orders(limit=1)
        assert len(orders) == 1
        assert orders[0].status == OrderStatus.CONFIRMED
        assert orders[0].quantity == 10
        assert orders[0].sku == "WIDGET-001"

    def test_list_orders_pagination(self, service):
        service.create_sku("WIDGET-001", "Widget A", 100)
        for i in range(5):
            res = service.create_reservation("WIDGET-001", 10, f"idem-{i}")
            service.confirm_reservation(res["reservation_id"])

        orders1 = service.list_orders(offset=0, limit=2)
        assert len(orders1["orders"]) == 2
        assert orders1["total"] == 5

        orders2 = service.list_orders(offset=2, limit=2)
        assert len(orders2["orders"]) == 2
