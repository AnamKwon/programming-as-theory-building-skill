import pytest
import tempfile
import os
from datetime import datetime, timedelta
import time
import sqlite3
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def repository(temp_db):
    return Repository(db_path=temp_db)


@pytest.fixture
def service(repository):
    return CommerceService(repository)


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SKU-001", 100)
        assert result['sku'] == "SKU-001"
        assert result['available_stock'] == 100
        assert result['total_stock'] == 100
        assert result['id'] is not None

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU-002", 50)
        result = service.adjust_stock("SKU-002", 25)
        assert result['available_stock'] == 75

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU-003", 100)
        result = service.adjust_stock("SKU-003", -30)
        assert result['available_stock'] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservationHappyPath:
    def test_reservation_happy_path(self, service):
        service.create_sku("SKU-004", 100)

        reservation = service.create_reservation("SKU-004", 30, "idempotency-1")
        assert reservation['status'] == 'PENDING'
        assert reservation['quantity'] == 30
        assert reservation['id'] is not None

        sku = service.repository.get_sku_by_name("SKU-004")
        assert sku['available_stock'] == 70

        order = service.confirm_reservation(reservation['id'])
        assert order['id'] is not None
        assert order['reservation_id'] == reservation['id']

        confirmed_res = service.repository.get_reservation(reservation['id'])
        assert confirmed_res['status'] == 'CONFIRMED'


class TestReservationIdempotency:
    def test_idempotent_retry_returns_cached(self, service):
        service.create_sku("SKU-005", 100)

        res1 = service.create_reservation("SKU-005", 20, "idempotency-key-1")
        sku_after_first = service.repository.get_sku_by_name("SKU-005")
        assert sku_after_first['available_stock'] == 80

        res2 = service.create_reservation("SKU-005", 20, "idempotency-key-1")
        assert res1['id'] == res2['id']
        assert res1 == res2

        sku_after_second = service.repository.get_sku_by_name("SKU-005")
        assert sku_after_second['available_stock'] == 80


class TestInsufficientStock:
    def test_insufficient_stock_returns_error(self, service):
        service.create_sku("SKU-006", 50)

        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU-006", 100, "idempotency-2")


class TestReservationExpiration:
    def test_expired_reservation_restores_stock(self, service, temp_db):
        service.create_sku("SKU-007", 100)

        reservation = service.create_reservation("SKU-007", 40, "idempotency-3")
        sku_after_res = service.repository.get_sku_by_name("SKU-007")
        assert sku_after_res['available_stock'] == 60

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=310)).isoformat()
        cursor.execute(
            'UPDATE reservations SET created_at = ? WHERE id = ?',
            (old_time, reservation['id'])
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError, match="Reservation expired"):
            service.confirm_reservation(reservation['id'])

        sku_after_expiry = service.repository.get_sku_by_name("SKU-007")
        assert sku_after_expiry['available_stock'] == 100

        expired_res = service.repository.get_reservation(reservation['id'])
        assert expired_res['status'] == 'EXPIRED'

    def test_valid_reservation_within_300_seconds(self, service):
        service.create_sku("SKU-008", 100)

        reservation = service.create_reservation("SKU-008", 25, "idempotency-4")

        order = service.confirm_reservation(reservation['id'])
        assert order['id'] is not None

        confirmed_res = service.repository.get_reservation(reservation['id'])
        assert confirmed_res['status'] == 'CONFIRMED'


class TestReservationCancellation:
    def test_cancel_pending_reservation_restores_stock(self, service):
        service.create_sku("SKU-009", 100)

        reservation = service.create_reservation("SKU-009", 35, "idempotency-5")
        sku_after_res = service.repository.get_sku_by_name("SKU-009")
        assert sku_after_res['available_stock'] == 65

        result = service.cancel_reservation(reservation['id'])
        assert result['status'] == 'CANCELLED'

        sku_after_cancel = service.repository.get_sku_by_name("SKU-009")
        assert sku_after_cancel['available_stock'] == 100

    def test_cancel_nonpending_fails(self, service):
        service.create_sku("SKU-010", 100)
        reservation = service.create_reservation("SKU-010", 20, "idempotency-6")

        service.confirm_reservation(reservation['id'])

        with pytest.raises(ValueError, match="Cannot cancel reservation with status"):
            service.cancel_reservation(reservation['id'])


class TestStateValidation:
    def test_confirm_non_pending_fails(self, service):
        service.create_sku("SKU-011", 100)
        reservation = service.create_reservation("SKU-011", 15, "idempotency-7")

        service.confirm_reservation(reservation['id'])

        with pytest.raises(ValueError, match="Cannot confirm reservation with status"):
            service.confirm_reservation(reservation['id'])


class TestOrders:
    def test_get_orders_pagination(self, service):
        service.create_sku("SKU-012", 200)

        for i in range(5):
            res = service.create_reservation("SKU-012", 10, f"idempotency-order-{i}")
            service.confirm_reservation(res['id'])

        result = service.get_orders(page=1, size=10)
        assert result['total'] == 5
        assert len(result['orders']) == 5
        assert result['page'] == 1
        assert result['size'] == 10

    def test_get_orders_pagination_offset(self, service):
        service.create_sku("SKU-013", 500)

        for i in range(25):
            res = service.create_reservation("SKU-013", 5, f"idempotency-order-{i}")
            service.confirm_reservation(res['id'])

        page1 = service.get_orders(page=1, size=10)
        page2 = service.get_orders(page=2, size=10)
        page3 = service.get_orders(page=3, size=10)

        assert len(page1['orders']) == 10
        assert len(page2['orders']) == 10
        assert len(page3['orders']) == 5
        assert page1['orders'][0]['id'] != page2['orders'][0]['id']
