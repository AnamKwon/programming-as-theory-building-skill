import pytest
import os
import tempfile
import sqlite3
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    db.initialize_schema()
    yield db
    os.unlink(path)


@pytest.fixture
def service(test_db):
    return CommerceService(test_db)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("SKU-001", 100)
        assert result["sku"] == "SKU-001"
        assert result["initial_stock"] == 100

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("SKU-002", 100)
        with pytest.raises(HTTPException) as exc_info:
            service.create_sku("SKU-002", 50)
        assert exc_info.value.status_code == 400

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU-003", 100)
        result = service.adjust_stock("SKU-003", 50)
        assert result.available_stock == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU-004", 100)
        result = service.adjust_stock("SKU-004", -30)
        assert result.available_stock == 70

    def test_adjust_nonexistent_sku_fails(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("NONEXISTENT", 10)
        assert exc_info.value.status_code == 404


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU-005", 100)
        result = service.create_reservation("SKU-005", 20, "idem-001")
        assert result.sku == "SKU-005"
        assert result.quantity == 20
        assert result.status == "PENDING"
        assert result.idempotency_key == "idem-001"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-006", 10)
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("SKU-006", 20, "idem-002")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Insufficient stock"

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("NONEXISTENT", 10, "idem-003")
        assert exc_info.value.status_code == 404

    def test_reservation_idempotency(self, service):
        service.create_sku("SKU-007", 100)
        result1 = service.create_reservation("SKU-007", 25, "idem-004")
        result2 = service.create_reservation("SKU-007", 25, "idem-004")

        assert result1.id == result2.id
        assert result1.created_at == result2.created_at

    def test_reservation_stock_deduction(self, service):
        service.create_sku("SKU-008", 100)
        service.create_reservation("SKU-008", 30, "idem-005")
        stock = service.sku_repo.get_sku_by_name("SKU-008")
        assert stock["available_stock"] == 70
        assert stock["reserved_stock"] == 30

    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU-009", 100)
        res = service.create_reservation("SKU-009", 15, "idem-006")
        order = service.confirm_reservation(res.id)
        assert order.reservation_id == res.id

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(999)
        assert exc_info.value.status_code == 404

    def test_confirm_non_pending_reservation(self, service):
        service.create_sku("SKU-010", 100)
        res = service.create_reservation("SKU-010", 10, "idem-007")
        service.confirm_reservation(res.id)

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res.id)
        assert exc_info.value.status_code == 400
        assert "not PENDING" in exc_info.value.detail

    def test_confirm_expired_reservation(self, service, test_db):
        service.create_sku("SKU-011", 100)
        res = service.create_reservation("SKU-011", 20, "idem-008")

        # Backdate the reservation to expire it
        conn = sqlite3.connect(test_db.db_path)
        cursor = conn.cursor()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res.id),
        )
        conn.commit()
        conn.close()

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res.id)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Reservation expired"

        # Verify stock was restored
        stock = service.sku_repo.get_sku_by_name("SKU-011")
        assert stock["available_stock"] == 100
        assert stock["reserved_stock"] == 0

    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU-012", 100)
        res = service.create_reservation("SKU-012", 25, "idem-009")
        result = service.cancel_reservation(res.id)
        assert result["status"] == "CANCELLED"

        # Verify stock was restored
        stock = service.sku_repo.get_sku_by_name("SKU-012")
        assert stock["available_stock"] == 100

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(999)
        assert exc_info.value.status_code == 404

    def test_cancel_non_pending_reservation(self, service):
        service.create_sku("SKU-013", 100)
        res = service.create_reservation("SKU-013", 10, "idem-010")
        service.confirm_reservation(res.id)

        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(res.id)
        assert exc_info.value.status_code == 400


class TestOrders:
    def test_get_orders_empty(self, service):
        result = service.get_orders_paginated(1, 10)
        assert result["orders"] == []
        assert result["total"] == 0

    def test_get_orders_pagination(self, service):
        service.create_sku("SKU-014", 1000)

        # Create 15 orders
        for i in range(15):
            res = service.create_reservation("SKU-014", 5, f"idem-order-{i}")
            service.confirm_reservation(res.id)

        # First page
        result = service.get_orders_paginated(1, 10)
        assert len(result["orders"]) == 10
        assert result["total"] == 15
        assert result["page"] == 1

        # Second page
        result = service.get_orders_paginated(2, 10)
        assert len(result["orders"]) == 5
        assert result["page"] == 2

    def test_get_orders_custom_page_size(self, service):
        service.create_sku("SKU-015", 1000)

        # Create 25 orders
        for i in range(25):
            res = service.create_reservation("SKU-015", 2, f"idem-order-custom-{i}")
            service.confirm_reservation(res.id)

        result = service.get_orders_paginated(1, 5)
        assert len(result["orders"]) == 5
        assert result["total"] == 25
        assert result["size"] == 5

        result = service.get_orders_paginated(3, 5)
        assert len(result["orders"]) == 5

    def test_get_orders_invalid_page(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.get_orders_paginated(0, 10)
        assert exc_info.value.status_code == 400

    def test_get_orders_invalid_size(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.get_orders_paginated(1, 0)
        assert exc_info.value.status_code == 400


class TestHappyPath:
    def test_full_workflow(self, service):
        # 1. Create SKU
        service.create_sku("SKU-HAPPY", 100)

        # 2. Create reservation
        res = service.create_reservation("SKU-HAPPY", 30, "idem-happy-001")
        assert res.status == "PENDING"
        assert res.sku == "SKU-HAPPY"

        # 3. Verify stock deducted
        stock = service.sku_repo.get_sku_by_name("SKU-HAPPY")
        assert stock["available_stock"] == 70
        assert stock["reserved_stock"] == 30

        # 4. Confirm reservation
        order = service.confirm_reservation(res.id)
        assert order.reservation_id == res.id

        # 5. Get orders
        orders = service.get_orders_paginated(1, 10)
        assert len(orders["orders"]) == 1
        assert orders["orders"][0].id == order.id

        # 6. Verify reservation is confirmed
        res_data = service.reservation_repo.get_reservation(res.id)
        assert res_data["status"] == "CONFIRMED"
