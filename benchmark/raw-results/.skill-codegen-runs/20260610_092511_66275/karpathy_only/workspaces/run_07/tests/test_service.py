import pytest
from datetime import datetime, timedelta

from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStock,
    NotFound,
    ReservationExpired,
)


@pytest.fixture
def repo():
    repository = Repository(":memory:")
    yield repository
    repository.clear_all()


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKU:
    def test_create_sku(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        assert sku["sku_code"] == "WIDGET-001"
        assert sku["quantity"] == 100
        assert sku["id"] is not None

    def test_adjust_stock_increase(self, service):
        sku = service.create_sku("WIDGET-001", 50)
        adjusted = service.adjust_stock(sku["id"], 25)
        assert adjusted["quantity"] == 75

    def test_adjust_stock_decrease(self, service):
        sku = service.create_sku("WIDGET-001", 50)
        adjusted = service.adjust_stock(sku["id"], -10)
        assert adjusted["quantity"] == 40

    def test_adjust_stock_insufficient(self, service):
        sku = service.create_sku("WIDGET-001", 50)
        with pytest.raises(ValueError):
            service.adjust_stock(sku["id"], -100)

    def test_adjust_stock_not_found(self, service):
        with pytest.raises(NotFound):
            service.adjust_stock(999, 10)


class TestReservation:
    def test_create_reservation_success(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        reservation = service.create_reservation(sku["id"], 10, "idempotent-key-1")
        assert reservation["sku_id"] == sku["id"]
        assert reservation["quantity"] == 10
        assert reservation["status"] == "pending"
        assert reservation["expires_at"] is not None

    def test_create_reservation_insufficient_stock(self, service):
        sku = service.create_sku("WIDGET-001", 10)
        with pytest.raises(InsufficientStock):
            service.create_reservation(sku["id"], 20, "idempotent-key-1")

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(NotFound):
            service.create_reservation(999, 10, "idempotent-key-1")

    def test_create_reservation_idempotent(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        key = "idempotent-key-2"
        res1 = service.create_reservation(sku["id"], 10, key)
        res2 = service.create_reservation(sku["id"], 10, key)
        assert res1["id"] == res2["id"]

    def test_create_reservation_expired_idempotent_retry(self, service, repo):
        sku = service.create_sku("WIDGET-001", 100)
        key = "idempotent-key-3"
        res = service.create_reservation(sku["id"], 10, key)

        # Mark as expired
        repo.update_reservation_status(res["id"], "expired")

        with pytest.raises(ReservationExpired):
            service.create_reservation(sku["id"], 10, key)

    def test_cancel_reservation_success(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        res = service.create_reservation(sku["id"], 10, "cancel-key-1")
        cancelled = service.cancel_reservation(res["id"])
        assert cancelled["status"] == "cancelled"

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(NotFound):
            service.cancel_reservation(999)

    def test_cancel_reservation_already_confirmed(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        res = service.create_reservation(sku["id"], 10, "confirm-key-1")
        service.confirm_reservation(res["id"])
        with pytest.raises(ValueError):
            service.cancel_reservation(res["id"])


class TestOrder:
    def test_confirm_reservation_success(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        res = service.create_reservation(sku["id"], 10, "order-key-1")
        order = service.confirm_reservation(res["id"])

        assert order["sku_id"] == sku["id"]
        assert order["quantity"] == 10
        assert order["state"] == "confirmed"
        assert order["reservation_id"] == res["id"]

    def test_confirm_reservation_deducts_stock(self, service):
        sku = service.create_sku("WIDGET-001", 100)
        res = service.create_reservation(sku["id"], 10, "stock-deduct-key-1")
        service.confirm_reservation(res["id"])

        updated_sku = service.repo.get_sku(sku["id"])
        assert updated_sku["quantity"] == 90

    def test_confirm_reservation_expired(self, service, repo):
        sku = service.create_sku("WIDGET-001", 100)
        res = service.create_reservation(sku["id"], 10, "expired-key-1")

        # Manually expire the reservation
        conn = repo._get_conn()
        cursor = conn.cursor()
        past_time = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        cursor.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past_time, res["id"]),
        )
        conn.commit()
        repo._close_conn(conn)

        with pytest.raises(ReservationExpired):
            service.confirm_reservation(res["id"])

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(NotFound):
            service.confirm_reservation(999)

    def test_list_orders_with_pagination(self, service):
        sku = service.create_sku("WIDGET-001", 1000)
        for i in range(25):
            res = service.create_reservation(sku["id"], 1, f"page-key-{i}")
            service.confirm_reservation(res["id"])

        page1 = service.list_orders(offset=0, limit=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 25
        assert page1["offset"] == 0
        assert page1["limit"] == 10

        page2 = service.list_orders(offset=10, limit=10)
        assert len(page2["items"]) == 10

        page3 = service.list_orders(offset=20, limit=10)
        assert len(page3["items"]) == 5

    def test_get_order_not_found(self, service):
        with pytest.raises(NotFound):
            service.get_order(999)
