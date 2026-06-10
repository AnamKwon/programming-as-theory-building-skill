import pytest
import os
import tempfile
from fastapi import HTTPException
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import ReservationState, OrderState


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def repo(temp_db):
    return Repository(db_path=temp_db)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKU:
    def test_create_sku(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        sku = repo.get_sku("WIDGET-A")
        assert sku["name"] == "Widget A"

    def test_create_duplicate_sku_raises_conflict(self, service):
        service.create_sku("WIDGET-A", "Widget A")
        with pytest.raises(HTTPException) as exc_info:
            service.create_sku("WIDGET-A", "Widget A Duplicate")
        assert exc_info.value.status_code == 409


class TestStock:
    def test_adjust_stock_for_nonexistent_sku_raises_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("MISSING", 100)
        assert exc_info.value.status_code == 404

    def test_adjust_stock_increases_available_quantity(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        result = service.adjust_stock("WIDGET-A", 100)
        assert result["available_quantity"] == 100
        assert result["reserved_quantity"] == 0

    def test_adjust_stock_negative_quantity(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)
        result = service.adjust_stock("WIDGET-A", -30)
        assert result["available_quantity"] == 70


class TestReservation:
    def test_create_reservation_success(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)

        res = service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)
        assert res.sku == "WIDGET-A"
        assert res.quantity == 10
        assert res.state == ReservationState.PENDING

        stock = repo.get_stock("WIDGET-A")
        assert stock["reserved_quantity"] == 10

    def test_create_reservation_insufficient_stock_raises_conflict(self, service):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 5)

        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)
        assert exc_info.value.status_code == 409

    def test_create_reservation_nonexistent_sku_raises_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("MISSING", 10, "idempotency-1", 3600)
        assert exc_info.value.status_code == 404

    def test_idempotent_reservation_retry(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)

        res1 = service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)
        res2 = service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)

        assert res1.id == res2.id
        stock = repo.get_stock("WIDGET-A")
        assert stock["reserved_quantity"] == 10

    def test_idempotent_retry_on_expired_reservation_raises(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)

        res = service.create_reservation("WIDGET-A", 10, "idempotency-1", 0)
        repo.update_reservation_state(res.id, ReservationState.EXPIRED.value)

        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)
        assert exc_info.value.status_code == 410

    def test_cancel_reservation_success(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)
        res = service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)

        cancelled = service.cancel_reservation(res.id)
        assert cancelled.state == ReservationState.CANCELLED

        stock = repo.get_stock("WIDGET-A")
        assert stock["reserved_quantity"] == 0

    def test_cancel_confirmed_reservation_raises_conflict(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)
        res = service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)
        service.confirm_reservation(res.id)

        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(res.id)
        assert exc_info.value.status_code == 409


class TestOrder:
    def test_confirm_reservation_creates_order(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)
        res = service.create_reservation("WIDGET-A", 10, "idempotency-1", 3600)

        order = service.confirm_reservation(res.id)
        assert order.sku == "WIDGET-A"
        assert order.quantity == 10
        assert order.state == OrderState.CONFIRMED

    def test_confirm_reservation_nonexistent_raises_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation("nonexistent-id")
        assert exc_info.value.status_code == 404

    def test_confirm_expired_reservation_raises_gone(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 100)
        res = service.create_reservation("WIDGET-A", 10, "idempotency-1", 0)

        import time
        time.sleep(0.1)

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res.id)
        assert exc_info.value.status_code == 410

    def test_list_orders_pagination(self, service, repo):
        service.create_sku("WIDGET-A", "Widget A")
        service.adjust_stock("WIDGET-A", 1000)

        for i in range(25):
            res = service.create_reservation("WIDGET-A", 10, f"idempotency-{i}", 3600)
            service.confirm_reservation(res.id)

        page1 = service.list_orders(page=1, page_size=10)
        assert len(page1["orders"]) == 10
        assert page1["total"] == 25
        assert page1["page"] == 1

        page2 = service.list_orders(page=2, page_size=10)
        assert len(page2["orders"]) == 10

        page3 = service.list_orders(page=3, page_size=10)
        assert len(page3["orders"]) == 5
