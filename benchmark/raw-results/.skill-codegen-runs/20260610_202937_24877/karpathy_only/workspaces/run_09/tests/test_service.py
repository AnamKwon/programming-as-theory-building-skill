import pytest
from datetime import datetime
from commerce_service.repository import Database, Repository
from commerce_service.service import (
    Service,
    InsufficientStockError,
    SKUNotFoundError,
    ReservationNotFoundError,
    ReservationNotPendingError,
    ReservationExpiredError,
    DuplicateIdempotencyKeyError,
)


@pytest.fixture
def db():
    database = Database(":memory:")
    database.connect()
    yield database
    database.disconnect()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def service(repo):
    return Service(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        response = service.create_sku("SKU001", 100)
        assert response.id > 0
        assert response.sku == "SKU001"
        assert response.available_stock == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU001", 50)
        response = service.adjust_stock("SKU001", 25)
        assert response.sku == "SKU001"
        assert response.previous_stock == 50
        assert response.adjusted_amount == 25
        assert response.new_stock == 75

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", 50)
        response = service.adjust_stock("SKU001", -20)
        assert response.new_stock == 30

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        response = service.create_reservation("SKU001", 25, "key-1")
        assert response.id > 0
        assert response.sku == "SKU001"
        assert response.quantity == 25
        assert response.status == "PENDING"
        assert response.idempotency_key == "key-1"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", 10)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 20, "key-1")

    def test_create_reservation_stock_deducted(self, service):
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "key-1")
        sku = service.repo.get_sku_by_name("SKU001")
        assert sku["available_stock"] == 70

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU001", 100)
        res1 = service.create_reservation("SKU001", 25, "key-1")

        with pytest.raises(DuplicateIdempotencyKeyError):
            service.create_reservation("SKU001", 30, "key-1")

    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 25, "key-1")
        confirmed = service.confirm_reservation(res.id)
        assert confirmed.status == "CONFIRMED"
        order = service.repo.get_order_by_id(1)
        assert order is not None
        assert order["reservation_id"] == res.id

    def test_confirm_reservation_not_pending(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 25, "key-1")
        service.confirm_reservation(res.id)
        with pytest.raises(ReservationNotPendingError):
            service.confirm_reservation(res.id)

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_confirm_reservation_expired(self, service):
        import time
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 25, "key-1")

        db = service.repo.db
        now = datetime.utcnow().isoformat()
        old_time = datetime.utcfromtimestamp(
            datetime.utcnow().timestamp() - 400
        ).isoformat()
        db.execute_update(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res.id),
        )

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res.id)

        updated = service.repo.get_reservation_by_id(res.id)
        assert updated["status"] == "EXPIRED"
        sku = service.repo.get_sku_by_name("SKU001")
        assert sku["available_stock"] == 100

    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 25, "key-1")
        cancelled = service.cancel_reservation(res.id)
        assert cancelled.status == "CANCELLED"
        sku = service.repo.get_sku_by_name("SKU001")
        assert sku["available_stock"] == 100

    def test_cancel_reservation_not_pending(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 25, "key-1")
        service.confirm_reservation(res.id)
        with pytest.raises(ReservationNotPendingError):
            service.cancel_reservation(res.id)

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)


class TestOrders:
    def test_get_orders_empty(self, service):
        response = service.get_orders(1, 10)
        assert response.page == 1
        assert response.size == 10
        assert response.total == 0
        assert len(response.orders) == 0

    def test_get_orders_pagination(self, service):
        service.create_sku("SKU001", 1000)
        for i in range(25):
            res = service.create_reservation("SKU001", 1, f"key-{i}")
            service.confirm_reservation(res.id)

        page1 = service.get_orders(1, 10)
        assert page1.page == 1
        assert page1.size == 10
        assert page1.total == 25
        assert len(page1.orders) == 10

        page2 = service.get_orders(2, 10)
        assert page2.page == 2
        assert len(page2.orders) == 10

        page3 = service.get_orders(3, 10)
        assert page3.page == 3
        assert len(page3.orders) == 5

    def test_get_orders_single_order(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 50, "key-1")
        service.confirm_reservation(res.id)

        response = service.get_orders(1, 10)
        assert response.total == 1
        assert len(response.orders) == 1
        assert response.orders[0].reservation_id == res.id


class TestCompleteWorkflow:
    def test_full_happy_path(self, service):
        service.create_sku("WIDGET", 100)
        res = service.create_reservation("WIDGET", 50, "order-123")
        assert res.status == "PENDING"
        assert res.quantity == 50

        confirmed = service.confirm_reservation(res.id)
        assert confirmed.status == "CONFIRMED"

        orders = service.get_orders(1, 10)
        assert orders.total == 1
        assert orders.orders[0].reservation_id == res.id
