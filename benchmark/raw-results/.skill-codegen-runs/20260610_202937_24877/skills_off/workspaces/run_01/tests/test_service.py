import pytest
import os
import time
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    test_db_path = "test_service_commerce.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    db = Database(test_db_path)
    yield db
    db.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.fixture
def service(test_db):
    return CommerceService(test_db)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("TEST-SKU", 100)
        assert result["sku"] == "TEST-SKU"
        assert result["available_stock"] == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU-1", 50)
        result = service.adjust_stock("SKU-1", 25)
        assert result["available_stock"] == 75

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU-2", 100)
        result = service.adjust_stock("SKU-2", -30)
        assert result["available_stock"] == 70

    def test_adjust_stock_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("NONEXISTENT", 10)
        assert exc_info.value.status_code == 404


class TestReservationOperations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU-RES", 100)
        reservation = service.create_reservation("SKU-RES", 25, "idem-key-1")
        assert reservation.sku == "SKU-RES"
        assert reservation.quantity == 25
        assert reservation.status == "PENDING"
        assert reservation.idempotency_key == "idem-key-1"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-LOW", 10)
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("SKU-LOW", 50, "idem-low")
        assert exc_info.value.status_code == 400
        assert "Insufficient stock" in str(exc_info.value.detail)

    def test_create_reservation_deducts_stock(self, service):
        service.create_sku("SKU-DEDUCT", 100)
        service.create_reservation("SKU-DEDUCT", 30, "idem-deduct")

        sku_data = service.sku_repo.get_sku_by_sku("SKU-DEDUCT")
        assert sku_data["available_stock"] == 70

    def test_create_reservation_idempotency(self, service):
        service.create_sku("SKU-IDEM", 100)
        res1 = service.create_reservation("SKU-IDEM", 25, "idem-same")
        res2 = service.create_reservation("SKU-IDEM", 25, "idem-same")

        assert res1.id == res2.id
        assert res1.quantity == res2.quantity

        sku_data = service.sku_repo.get_sku_by_sku("SKU-IDEM")
        assert sku_data["available_stock"] == 75

    def test_create_reservation_sku_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("MISSING-SKU", 10, "idem-missing")
        assert exc_info.value.status_code == 404


class TestConfirmReservation:
    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU-CONFIRM", 100)
        reservation = service.create_reservation("SKU-CONFIRM", 20, "idem-confirm")

        confirmed = service.confirm_reservation(reservation.id)
        assert confirmed.status == "CONFIRMED"

    def test_confirm_reservation_creates_order(self, service):
        service.create_sku("SKU-ORDER", 100)
        reservation = service.create_reservation("SKU-ORDER", 15, "idem-order")

        service.confirm_reservation(reservation.id)

        orders, total = service.order_repo.list_orders(1, 10)
        assert total == 1
        assert orders[0]["reservation_id"] == reservation.id

    def test_confirm_reservation_not_pending(self, service):
        service.create_sku("SKU-NOTPENDING", 100)
        reservation = service.create_reservation("SKU-NOTPENDING", 10, "idem-notpending")

        service.confirm_reservation(reservation.id)

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(reservation.id)
        assert exc_info.value.status_code == 400
        assert "not pending" in str(exc_info.value.detail)

    def test_confirm_reservation_expired(self, service):
        service.create_sku("SKU-EXPIRE", 100)
        reservation = service.create_reservation("SKU-EXPIRE", 25, "idem-expire")

        service.reservation_repo.update_reservation_status(
            reservation.id, "PENDING"
        )
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
        conn = service.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation.id),
        )
        conn.commit()

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(reservation.id)
        assert exc_info.value.status_code == 400
        assert "expired" in str(exc_info.value.detail)

        updated_res = service.reservation_repo.get_reservation_by_id(reservation.id)
        assert updated_res["status"] == "EXPIRED"

        sku_data = service.sku_repo.get_sku_by_sku("SKU-EXPIRE")
        assert sku_data["available_stock"] == 100

    def test_confirm_reservation_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(999)
        assert exc_info.value.status_code == 404


class TestCancelReservation:
    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU-CANCEL", 100)
        reservation = service.create_reservation("SKU-CANCEL", 20, "idem-cancel")

        cancelled = service.cancel_reservation(reservation.id)
        assert cancelled.status == "CANCELLED"

    def test_cancel_reservation_restores_stock(self, service):
        service.create_sku("SKU-RESTORE", 100)
        reservation = service.create_reservation("SKU-RESTORE", 35, "idem-restore")

        sku_before = service.sku_repo.get_sku_by_sku("SKU-RESTORE")
        assert sku_before["available_stock"] == 65

        service.cancel_reservation(reservation.id)

        sku_after = service.sku_repo.get_sku_by_sku("SKU-RESTORE")
        assert sku_after["available_stock"] == 100

    def test_cancel_reservation_not_pending(self, service):
        service.create_sku("SKU-CANCEL-CONFIRM", 100)
        reservation = service.create_reservation("SKU-CANCEL-CONFIRM", 10, "idem-cancel-confirm")

        service.confirm_reservation(reservation.id)

        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(reservation.id)
        assert exc_info.value.status_code == 400
        assert "not pending" in str(exc_info.value.detail)

    def test_cancel_reservation_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(999)
        assert exc_info.value.status_code == 404


class TestGetOrders:
    def test_get_orders_empty(self, service):
        result = service.get_orders(1, 10)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["size"] == 10

    def test_get_orders_pagination(self, service):
        service.create_sku("SKU-PAGINATE", 500)

        for i in range(25):
            reservation = service.create_reservation(
                "SKU-PAGINATE", 10, f"idem-page-{i}"
            )
            service.confirm_reservation(reservation.id)

        page1 = service.get_orders(1, 10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 25
        assert page1["page"] == 1

        page2 = service.get_orders(2, 10)
        assert len(page2["items"]) == 10
        assert page2["page"] == 2

        page3 = service.get_orders(3, 10)
        assert len(page3["items"]) == 5
        assert page3["page"] == 3

    def test_get_orders_invalid_page(self, service):
        result = service.get_orders(0, 10)
        assert result["page"] == 1

    def test_get_orders_invalid_size(self, service):
        result = service.get_orders(1, -5)
        assert result["size"] == 10
