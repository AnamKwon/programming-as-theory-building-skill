import pytest
import tempfile
import os
from datetime import datetime, timedelta
from fastapi import HTTPException

from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repo(temp_db):
    return Repository(temp_db)


@pytest.fixture
def service(repo):
    return Service(repo)


class TestSKU:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", 100)
        assert result["sku"] == "SKU001"
        assert result["stock"] == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["stock"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("NONEXISTENT", 10)
        assert exc_info.value.status_code == 404


class TestReservation:
    def test_create_reservation(self, service):
        service.create_sku("SKU001", 100)
        result = service.create_reservation("SKU001", 30, "idempotency-1")
        assert result["id"] == 1
        assert result["sku"] == "SKU001"
        assert result["quantity"] == 30
        assert result["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", 20)
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("SKU001", 50, "idempotency-1")
        assert exc_info.value.status_code == 400
        assert "Insufficient stock" in exc_info.value.detail

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("NONEXISTENT", 10, "idempotency-1")
        assert exc_info.value.status_code == 404

    def test_idempotency_key_returns_existing(self, service):
        service.create_sku("SKU001", 100)
        result1 = service.create_reservation("SKU001", 30, "idempotency-1")
        result2 = service.create_reservation("SKU001", 30, "idempotency-1")

        assert result1["id"] == result2["id"]
        assert result1 == result2

    def test_idempotency_no_double_deduction(self, service):
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "idempotency-1")
        service.create_reservation("SKU001", 30, "idempotency-1")

        stock = service.repo.get_sku_stock("SKU001")
        assert stock == 70

    def test_confirm_reservation(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "idempotency-1")
        result = service.confirm_reservation(res["id"])

        assert result["status"] == "CONFIRMED"
        assert "order_id" in result

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(999)
        assert exc_info.value.status_code == 404

    def test_confirm_non_pending_reservation(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "idempotency-1")
        service.confirm_reservation(res["id"])

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res["id"])
        assert exc_info.value.status_code == 400

    def test_expired_reservation_rejection(self, service, repo):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "idempotency-1")
        res_id = res["id"]

        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        import sqlite3
        conn = repo.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (old_time, res_id))
        conn.commit()
        conn.close()

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res_id)
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail.lower()

        updated_res = repo.get_reservation(res_id)
        assert updated_res["status"] == "EXPIRED"

        stock = repo.get_sku_stock("SKU001")
        assert stock == 100

    def test_cancel_reservation(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "idempotency-1")
        result = service.cancel_reservation(res["id"])

        assert result["status"] == "CANCELLED"
        stock = service.repo.get_sku_stock("SKU001")
        assert stock == 100

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(999)
        assert exc_info.value.status_code == 404

    def test_cancel_non_pending_reservation(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "idempotency-1")
        service.confirm_reservation(res["id"])

        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(res["id"])
        assert exc_info.value.status_code == 400


class TestOrders:
    def test_get_orders_empty(self, service):
        result = service.get_orders()
        assert result["orders"] == []
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 0

    def test_get_orders_with_data(self, service):
        service.create_sku("SKU001", 100)
        res = service.create_reservation("SKU001", 30, "idempotency-1")
        service.confirm_reservation(res["id"])

        result = service.get_orders()
        assert len(result["orders"]) == 1
        assert result["orders"][0]["sku"] == "SKU001"
        assert result["orders"][0]["quantity"] == 30
        assert result["total"] == 1

    def test_get_orders_pagination(self, service):
        service.create_sku("SKU001", 1000)

        for i in range(15):
            res = service.create_reservation("SKU001", 10, f"idempotency-{i}")
            service.confirm_reservation(res["id"])

        page1 = service.get_orders(page=1, size=10)
        assert len(page1["orders"]) == 10
        assert page1["page"] == 1
        assert page1["total"] == 15

        page2 = service.get_orders(page=2, size=10)
        assert len(page2["orders"]) == 5
        assert page2["page"] == 2
