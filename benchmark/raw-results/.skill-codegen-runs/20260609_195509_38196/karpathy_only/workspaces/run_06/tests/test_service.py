import pytest
from datetime import datetime, timedelta
from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    CommerceService,
    ReservationError,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    DuplicateReservationError,
)
from src.commerce_service.models import ReservationStatus


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKUOperations:
    def test_create_sku(self, service):
        sku = service.create_sku("PROD-001", 100)
        assert sku["sku"] == "PROD-001"
        assert sku["stock"] == 100
        assert sku["reserved"] == 0
        assert sku["available"] == 100

    def test_create_duplicate_sku_raises_error(self, service):
        service.create_sku("PROD-001", 100)
        with pytest.raises(ReservationError, match="already exists"):
            service.create_sku("PROD-001", 50)

    def test_get_nonexistent_sku_raises_error(self, service):
        with pytest.raises(ReservationError, match="not found"):
            service.get_sku("NONEXISTENT")

    def test_adjust_stock_increases(self, service):
        service.create_sku("PROD-001", 100)
        sku = service.adjust_stock("PROD-001", 50)
        assert sku["stock"] == 150

    def test_adjust_stock_decreases(self, service):
        service.create_sku("PROD-001", 100)
        sku = service.adjust_stock("PROD-001", -30)
        assert sku["stock"] == 70

    def test_adjust_stock_below_zero_raises_error(self, service):
        service.create_sku("PROD-001", 100)
        with pytest.raises(ReservationError, match="Cannot adjust stock below 0"):
            service.adjust_stock("PROD-001", -150)


class TestReservationCreation:
    def test_create_reservation_success(self, service):
        service.create_sku("PROD-001", 100)
        res = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        assert res["sku"] == "PROD-001"
        assert res["quantity"] == 10
        assert res["status"] == ReservationStatus.PENDING
        assert res["customer_id"] == "customer-1"

    def test_create_reservation_reserves_stock(self, service):
        service.create_sku("PROD-001", 100)
        service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        sku = service.get_sku("PROD-001")
        assert sku["reserved"] == 10
        assert sku["available"] == 90

    def test_create_reservation_insufficient_stock_raises_error(self, service):
        service.create_sku("PROD-001", 100)
        with pytest.raises(InsufficientStockError, match="Insufficient stock"):
            service.create_reservation(
                sku="PROD-001",
                quantity=150,
                idempotency_key="idempotent-1",
                customer_id="customer-1",
            )

    def test_create_reservation_idempotent_retry(self, service):
        service.create_sku("PROD-001", 100)
        res1 = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        res2 = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        assert res1["id"] == res2["id"]
        sku = service.get_sku("PROD-001")
        assert sku["reserved"] == 10

    def test_create_reservation_nonexistent_sku_raises_error(self, service):
        with pytest.raises(ReservationError, match="not found"):
            service.create_reservation(
                sku="NONEXISTENT",
                quantity=10,
                idempotency_key="idempotent-1",
                customer_id="customer-1",
            )


class TestReservationConfirmation:
    def test_confirm_pending_reservation_creates_order(self, service):
        service.create_sku("PROD-001", 100)
        res = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        confirmed = service.confirm_reservation(
            reservation_id=res["id"],
            idempotency_key="idempotent-1",
        )
        assert confirmed["status"] == ReservationStatus.CONFIRMED
        assert "order_id" in confirmed

    def test_confirm_nonexistent_reservation_raises_error(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(
                reservation_id="nonexistent",
                idempotency_key="key",
            )

    def test_confirm_idempotent(self, service):
        service.create_sku("PROD-001", 100)
        res = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        confirmed1 = service.confirm_reservation(
            reservation_id=res["id"],
            idempotency_key="idempotent-1",
        )
        confirmed2 = service.confirm_reservation(
            reservation_id=res["id"],
            idempotency_key="idempotent-1",
        )
        assert confirmed1["order_id"] == confirmed2["order_id"]

    def test_confirm_expired_reservation_raises_error(self, service, repo):
        service.create_sku("PROD-001", 100)

        res_data = repo.create_reservation(
            reservation_id="res-1",
            sku="PROD-001",
            quantity=10,
            customer_id="customer-1",
            idempotency_key="idempotent-1",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )

        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(
                reservation_id="res-1",
                idempotency_key="idempotent-1",
            )


class TestReservationCancellation:
    def test_cancel_pending_reservation(self, service):
        service.create_sku("PROD-001", 100)
        res = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        cancelled = service.cancel_reservation(res["id"])
        assert cancelled["status"] == ReservationStatus.CANCELLED

    def test_cancel_releases_reserved_stock(self, service):
        service.create_sku("PROD-001", 100)
        res = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        service.cancel_reservation(res["id"])
        sku = service.get_sku("PROD-001")
        assert sku["reserved"] == 0
        assert sku["available"] == 100

    def test_cancel_confirmed_reservation_raises_error(self, service):
        service.create_sku("PROD-001", 100)
        res = service.create_reservation(
            sku="PROD-001",
            quantity=10,
            idempotency_key="idempotent-1",
            customer_id="customer-1",
        )
        service.confirm_reservation(
            reservation_id=res["id"],
            idempotency_key="idempotent-1",
        )
        with pytest.raises(InvalidStateTransitionError):
            service.cancel_reservation(res["id"])

    def test_cancel_nonexistent_reservation_raises_error(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("nonexistent")


class TestOrderLookup:
    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["total"] == 0
        assert result["items"] == []
        assert result["page"] == 1

    def test_list_orders_with_pagination(self, service):
        service.create_sku("PROD-001", 100)

        for i in range(25):
            res = service.create_reservation(
                sku="PROD-001",
                quantity=1,
                idempotency_key=f"idempotent-{i}",
                customer_id=f"customer-{i}",
            )
            service.confirm_reservation(
                reservation_id=res["id"],
                idempotency_key=f"idempotent-{i}",
            )

        page1 = service.list_orders(page=1, page_size=10)
        assert page1["total"] == 25
        assert len(page1["items"]) == 10
        assert page1["page"] == 1
        assert page1["total_pages"] == 3

        page2 = service.list_orders(page=2, page_size=10)
        assert len(page2["items"]) == 10

        page3 = service.list_orders(page=3, page_size=10)
        assert len(page3["items"]) == 5
