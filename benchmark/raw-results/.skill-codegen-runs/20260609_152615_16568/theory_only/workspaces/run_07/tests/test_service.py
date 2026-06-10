import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from commerce_service.models import Base, ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidReservationStatusError,
    SKUNotFoundError,
)


@pytest.fixture
def db():
    """In-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    yield session
    session.close()


@pytest.fixture
def repo(db):
    """Repository instance."""
    return Repository(db)


@pytest.fixture
def service(repo):
    """Service instance with 15-minute reservation TTL."""
    return CommerceService(repo, reservation_ttl_minutes=15)


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("WIDGET-001", 100)
        assert result["id"] == 1
        assert result["name"] == "WIDGET-001"
        assert result["stock_level"] == 100

    def test_adjust_stock_increase(self, service, repo):
        service.create_sku("WIDGET-002", 50)
        result = service.adjust_stock(1, 25)
        assert result["stock_level"] == 75

    def test_adjust_stock_decrease(self, service, repo):
        service.create_sku("WIDGET-003", 50)
        result = service.adjust_stock(1, -20)
        assert result["stock_level"] == 30

    def test_adjust_stock_nonexistent(self, service):
        with pytest.raises(ValueError):
            service.adjust_stock(999, 10)


class TestReservationHappyPath:
    def test_create_reservation_success(self, service):
        service.create_sku("WIDGET-004", 100)
        result = service.create_reservation(1, 50)
        assert result["sku_id"] == 1
        assert result["quantity"] == 50
        assert result["status"] == "pending"

    def test_confirm_reservation(self, service):
        service.create_sku("WIDGET-005", 100)
        res = service.create_reservation(1, 30)
        order = service.confirm_reservation(res["id"])
        assert order["status"] == "pending"
        assert order["quantity"] == 30

    def test_cancel_reservation(self, service):
        service.create_sku("WIDGET-006", 100)
        res = service.create_reservation(1, 20)
        result = service.cancel_reservation(res["id"])
        assert result["status"] == "cancelled"


class TestInsufficientStock:
    def test_reserve_exceeds_stock(self, service):
        service.create_sku("WIDGET-007", 50)
        with pytest.raises(InsufficientStockError) as exc:
            service.create_reservation(1, 100)
        assert "has 50 in stock, requested 100" in str(exc.value)

    def test_reserve_exactly_available(self, service):
        service.create_sku("WIDGET-008", 50)
        result = service.create_reservation(1, 50)
        assert result["quantity"] == 50

    def test_sku_not_found(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation(999, 10)


class TestIdempotencyKey:
    def test_idempotent_reservation_retry(self, service):
        service.create_sku("WIDGET-009", 100)
        key = "my-unique-key-123"
        res1 = service.create_reservation(1, 25, idempotency_key=key)
        res2 = service.create_reservation(1, 50, idempotency_key=key)
        assert res1["id"] == res2["id"]
        assert res2["quantity"] == 25

    def test_idempotency_different_keys(self, service):
        service.create_sku("WIDGET-010", 100)
        res1 = service.create_reservation(1, 20, idempotency_key="key1")
        res2 = service.create_reservation(1, 30, idempotency_key="key2")
        assert res1["id"] != res2["id"]

    def test_idempotency_returned_even_if_confirmed(self, service):
        service.create_sku("WIDGET-011", 50)
        key = "confirmed-key"
        res = service.create_reservation(1, 30, idempotency_key=key)
        service.confirm_reservation(res["id"])
        res2 = service.create_reservation(1, 20, idempotency_key=key)
        assert res2["id"] == res["id"]
        assert res2["status"] == "confirmed"


class TestReservationExpiration:
    def test_confirm_expired_reservation(self, service, repo):
        service.create_sku("WIDGET-012", 100)
        res = service.create_reservation(1, 30)
        reservation = repo.get_reservation(res["id"])
        reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
        repo.session.commit()
        with pytest.raises(ReservationExpiredError):
            service.confirm_reservation(res["id"])

    def test_expired_reservation_marked_expired(self, service, repo):
        service.create_sku("WIDGET-013", 100)
        res = service.create_reservation(1, 20)
        reservation = repo.get_reservation(res["id"])
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        repo.session.commit()
        try:
            service.confirm_reservation(res["id"])
        except ReservationExpiredError:
            pass
        updated = repo.get_reservation(res["id"])
        assert updated.status == ReservationStatus.EXPIRED


class TestReservationStateTransitions:
    def test_cannot_confirm_non_pending(self, service):
        service.create_sku("WIDGET-014", 100)
        res = service.create_reservation(1, 25)
        service.confirm_reservation(res["id"])
        with pytest.raises(InvalidReservationStatusError):
            service.confirm_reservation(res["id"])

    def test_cannot_cancel_already_cancelled(self, service):
        service.create_sku("WIDGET-015", 100)
        res = service.create_reservation(1, 25)
        service.cancel_reservation(res["id"])
        with pytest.raises(InvalidReservationStatusError):
            service.cancel_reservation(res["id"])

    def test_confirm_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation(999)

    def test_cancel_not_found(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation(999)


class TestOrderLookup:
    def test_list_orders_empty(self, service):
        result = service.list_orders()
        assert result["total"] == 0
        assert result["items"] == []
        assert result["skip"] == 0
        assert result["limit"] == 20

    def test_list_orders_pagination(self, service):
        service.create_sku("WIDGET-016", 100)
        for i in range(5):
            res = service.create_reservation(1, 10)
            service.confirm_reservation(res["id"])

        page1 = service.list_orders(skip=0, limit=2)
        assert len(page1["items"]) == 2
        assert page1["total"] == 5
        assert page1["skip"] == 0
        assert page1["limit"] == 2

        page2 = service.list_orders(skip=2, limit=2)
        assert len(page2["items"]) == 2

        page3 = service.list_orders(skip=4, limit=2)
        assert len(page3["items"]) == 1

    def test_list_orders_custom_limit(self, service):
        service.create_sku("WIDGET-017", 200)
        for i in range(3):
            res = service.create_reservation(1, 20)
            service.confirm_reservation(res["id"])

        result = service.list_orders(skip=0, limit=1)
        assert len(result["items"]) == 1
        assert result["total"] == 3
