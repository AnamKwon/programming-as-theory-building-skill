import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.commerce_service.repository import (
    Repository,
    Base,
    engine,
    SessionLocal,
)
from src.commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidReservationStateError,
    SKUNotFoundError,
)


@pytest.fixture
def session():
    """Create a fresh database session for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(session: Session):
    """Create a service instance with test database."""
    return Service(Repository(session))


class TestSKUOperations:
    def test_create_sku(self, service: Service):
        result = service.create_sku("SKU001", "Product A", 100)
        assert result["sku_id"] == "SKU001"
        assert result["name"] == "Product A"
        assert result["stock"] == 100

    def test_adjust_stock(self, service: Service):
        service.create_sku("SKU002", "Product B", 50)
        result = service.adjust_stock("SKU002", 25)
        assert result["stock"] == 75

        result = service.adjust_stock("SKU002", -10)
        assert result["stock"] == 65

    def test_adjust_stock_sku_not_found(self, service: Service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservationCreation:
    def test_create_reservation_success(self, service: Service):
        service.create_sku("SKU003", "Product C", 100)
        result = service.create_reservation("SKU003", 20, "idempotency-key-1")
        assert result["reservation_id"]
        assert result["sku_id"] == "SKU003"
        assert result["quantity"] == 20
        assert result["state"] == "pending"

    def test_create_reservation_idempotent(self, service: Service):
        service.create_sku("SKU004", "Product D", 100)
        result1 = service.create_reservation("SKU004", 20, "idempotency-key-2")
        result2 = service.create_reservation("SKU004", 30, "idempotency-key-2")
        assert result1["reservation_id"] == result2["reservation_id"]
        assert result2["quantity"] == 20  # Returns original quantity

    def test_create_reservation_insufficient_stock(self, service: Service):
        service.create_sku("SKU005", "Product E", 10)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU005", 20, "idempotency-key-3")

    def test_create_reservation_sku_not_found(self, service: Service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("MISSING", 10, "idempotency-key-4")


class TestReservationConfirmation:
    def test_confirm_reservation_success(self, service: Service):
        service.create_sku("SKU006", "Product F", 100)
        res = service.create_reservation("SKU006", 30, "idempotency-key-5")
        confirmed = service.confirm_reservation(res["reservation_id"], "idempotency-key-5")
        assert confirmed["state"] == "confirmed"

    def test_confirm_reservation_deducts_stock(self, service: Service):
        service.create_sku("SKU007", "Product G", 100)
        res = service.create_reservation("SKU007", 25, "idempotency-key-6")
        service.confirm_reservation(res["reservation_id"], "idempotency-key-6")
        # Stock should be reduced by reservation quantity
        # Verify by trying to create another reservation
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU007", 76, "idempotency-key-7")

    def test_confirm_reservation_not_found(self, service: Service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("MISSING", "idempotency-key-8")

    def test_confirm_reservation_idempotency_key_mismatch(self, service: Service):
        service.create_sku("SKU008", "Product H", 100)
        res = service.create_reservation("SKU008", 20, "idempotency-key-9")
        with pytest.raises(InvalidReservationStateError):
            service.confirm_reservation(res["reservation_id"], "wrong-key")

    def test_confirm_expired_reservation(self, service: Service, session: Session):
        service.create_sku("SKU009", "Product I", 100)
        res = service.create_reservation("SKU009", 20, "idempotency-key-10")

        # Manually expire the reservation
        from src.commerce_service.repository import ReservationModel
        reservation = session.query(ReservationModel).filter_by(id=res["reservation_id"]).first()
        reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
        session.commit()

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res["reservation_id"], "idempotency-key-10")

    def test_confirm_already_confirmed_reservation(self, service: Service):
        service.create_sku("SKU010", "Product J", 100)
        res = service.create_reservation("SKU010", 20, "idempotency-key-11")
        service.confirm_reservation(res["reservation_id"], "idempotency-key-11")
        with pytest.raises(InvalidReservationStateError):
            service.confirm_reservation(res["reservation_id"], "idempotency-key-11")


class TestReservationCancellation:
    def test_cancel_pending_reservation(self, service: Service):
        service.create_sku("SKU011", "Product K", 100)
        res = service.create_reservation("SKU011", 20, "idempotency-key-12")
        cancelled = service.cancel_reservation(res["reservation_id"], "idempotency-key-12")
        assert cancelled["state"] == "cancelled"

    def test_cancel_confirmed_reservation_returns_stock(self, service: Service):
        service.create_sku("SKU012", "Product L", 100)
        res = service.create_reservation("SKU012", 20, "idempotency-key-13")
        service.confirm_reservation(res["reservation_id"], "idempotency-key-13")
        service.cancel_reservation(res["reservation_id"], "idempotency-key-13")
        # Stock should be returned
        res2 = service.create_reservation("SKU012", 80, "idempotency-key-14")
        assert res2["state"] == "pending"

    def test_cancel_not_found(self, service: Service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("MISSING", "idempotency-key-15")


class TestOrderOperations:
    def test_create_order_success(self, service: Service):
        service.create_sku("SKU013", "Product M", 100)
        res = service.create_reservation("SKU013", 20, "idempotency-key-16")
        service.confirm_reservation(res["reservation_id"], "idempotency-key-16")
        order = service.create_order(res["reservation_id"], "order-idempotency-1")
        assert order["order_id"]
        assert order["reservation_id"] == res["reservation_id"]
        assert order["state"] == "pending"

    def test_create_order_idempotent(self, service: Service):
        service.create_sku("SKU014", "Product N", 100)
        res = service.create_reservation("SKU014", 20, "idempotency-key-17")
        service.confirm_reservation(res["reservation_id"], "idempotency-key-17")
        order1 = service.create_order(res["reservation_id"], "order-idempotency-2")
        order2 = service.create_order(res["reservation_id"], "order-idempotency-2")
        assert order1["order_id"] == order2["order_id"]

    def test_create_order_requires_confirmed_reservation(self, service: Service):
        service.create_sku("SKU015", "Product O", 100)
        res = service.create_reservation("SKU015", 20, "idempotency-key-18")
        with pytest.raises(InvalidReservationStateError):
            service.create_order(res["reservation_id"], "order-idempotency-3")

    def test_get_order(self, service: Service):
        service.create_sku("SKU016", "Product P", 100)
        res = service.create_reservation("SKU016", 20, "idempotency-key-19")
        service.confirm_reservation(res["reservation_id"], "idempotency-key-19")
        order = service.create_order(res["reservation_id"], "order-idempotency-4")
        retrieved = service.get_order(order["order_id"])
        assert retrieved["order_id"] == order["order_id"]

    def test_list_orders_pagination(self, service: Service):
        service.create_sku("SKU017", "Product Q", 1000)
        for i in range(15):
            res = service.create_reservation("SKU017", 10, f"idempotency-key-{100+i}")
            service.confirm_reservation(res["reservation_id"], f"idempotency-key-{100+i}")
            service.create_order(res["reservation_id"], f"order-idempotency-{100+i}")

        page1 = service.list_orders(limit=10, offset=0)
        assert len(page1["orders"]) == 10
        assert page1["total"] == 15
        assert page1["limit"] == 10
        assert page1["offset"] == 0

        page2 = service.list_orders(limit=10, offset=10)
        assert len(page2["orders"]) == 5
        assert page2["total"] == 15
