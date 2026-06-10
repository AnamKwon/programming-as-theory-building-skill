import pytest
import os
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

from src.commerce_service.service import CommerceService
from src.commerce_service.repository import Repository, init_db, DB_PATH, get_db_connection


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


class TestCommerceService:

    def test_create_sku(self):
        sku_id = CommerceService.create_sku("SKU-001", 100)
        assert sku_id is not None
        assert Repository.get_sku_stock("SKU-001") == 100

    def test_adjust_stock(self):
        CommerceService.create_sku("SKU-001", 100)
        updated = CommerceService.adjust_stock("SKU-001", 50)
        assert updated == 150

        updated = CommerceService.adjust_stock("SKU-001", -30)
        assert updated == 120

    def test_create_reservation_success(self):
        CommerceService.create_sku("SKU-001", 100)
        reservation = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        assert reservation["id"] is not None
        assert reservation["sku"] == "SKU-001"
        assert reservation["quantity"] == 50
        assert reservation["status"] == "PENDING"
        assert Repository.get_sku_stock("SKU-001") == 50

    def test_create_reservation_insufficient_stock(self):
        CommerceService.create_sku("SKU-001", 30)
        with pytest.raises(ValueError, match="Insufficient stock"):
            CommerceService.create_reservation("SKU-001", 50, "idempotency-1")

    def test_create_reservation_idempotency(self):
        CommerceService.create_sku("SKU-001", 100)
        res1 = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        stock_after_first = Repository.get_sku_stock("SKU-001")
        assert stock_after_first == 50

        res2 = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        assert res1["id"] == res2["id"]
        assert Repository.get_sku_stock("SKU-001") == 50

    def test_confirm_reservation_success(self):
        CommerceService.create_sku("SKU-001", 100)
        reservation = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        result = CommerceService.confirm_reservation(reservation["id"])
        assert result["status"] == "CONFIRMED"

        updated_reservation = Repository.get_reservation(reservation["id"])
        assert updated_reservation["status"] == "CONFIRMED"

    def test_confirm_reservation_expired(self):
        CommerceService.create_sku("SKU-001", 100)

        old_time = datetime.utcnow() - timedelta(seconds=301)
        with patch("src.commerce_service.service.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = old_time
            mock_datetime.fromisoformat = datetime.fromisoformat
            reservation = CommerceService.create_reservation(
                "SKU-001", 50, "idempotency-1"
            )

        with pytest.raises(ValueError, match="Reservation expired"):
            CommerceService.confirm_reservation(reservation["id"])

        updated_reservation = Repository.get_reservation(reservation["id"])
        assert updated_reservation["status"] == "EXPIRED"
        assert Repository.get_sku_stock("SKU-001") == 100

    def test_confirm_non_pending_reservation(self):
        CommerceService.create_sku("SKU-001", 100)
        reservation = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        CommerceService.confirm_reservation(reservation["id"])

        with pytest.raises(ValueError, match="Cannot confirm reservation"):
            CommerceService.confirm_reservation(reservation["id"])

    def test_cancel_reservation_success(self):
        CommerceService.create_sku("SKU-001", 100)
        reservation = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        assert Repository.get_sku_stock("SKU-001") == 50

        result = CommerceService.cancel_reservation(reservation["id"])
        assert result["status"] == "CANCELLED"
        assert Repository.get_sku_stock("SKU-001") == 100

    def test_cancel_non_pending_reservation(self):
        CommerceService.create_sku("SKU-001", 100)
        reservation = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )

        CommerceService.confirm_reservation(reservation["id"])

        with pytest.raises(ValueError, match="Cannot cancel reservation"):
            CommerceService.cancel_reservation(reservation["id"])

    def test_get_orders_pagination(self):
        CommerceService.create_sku("SKU-001", 1000)

        for i in range(15):
            res = CommerceService.create_reservation(
                "SKU-001", 10, f"idempotency-{i}"
            )
            CommerceService.confirm_reservation(res["id"])

        orders, total = CommerceService.get_orders(page=1, size=10)
        assert len(orders) == 10
        assert total == 15

        orders, total = CommerceService.get_orders(page=2, size=10)
        assert len(orders) == 5
        assert total == 15

    def test_full_workflow(self):
        CommerceService.create_sku("SKU-001", 100)

        reservation = CommerceService.create_reservation(
            "SKU-001", 50, "idempotency-1"
        )
        assert reservation["status"] == "PENDING"
        assert Repository.get_sku_stock("SKU-001") == 50

        confirmation = CommerceService.confirm_reservation(reservation["id"])
        assert confirmation["status"] == "CONFIRMED"

        orders, total = CommerceService.get_orders(page=1, size=10)
        assert total == 1
        assert orders[0]["reservation_id"] == reservation["id"]
