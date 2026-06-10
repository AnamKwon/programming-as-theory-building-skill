import pytest
import os
from datetime import datetime, timezone, timedelta
from commerce_service.repository import Database
from commerce_service.service import InventoryService


@pytest.fixture
def test_db():
    db_path = "test_commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def service(test_db):
    return InventoryService(test_db)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result['sku'] == "SKU001"
    assert result['available_stock'] == 100


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -10)
    assert result['available_stock'] == 90


def test_reserve_stock_sufficient(service):
    service.create_sku("SKU001", 100)
    reservation, status_code = service.reserve_stock("SKU001", 50, "key1")
    assert status_code == 201
    assert reservation['quantity'] == 50
    assert reservation['status'] == 'PENDING'


def test_reserve_stock_insufficient(service):
    service.create_sku("SKU001", 100)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.reserve_stock("SKU001", 150, "key1")


def test_reserve_stock_idempotency(service):
    service.create_sku("SKU001", 100)
    reservation1, status1 = service.reserve_stock("SKU001", 50, "key1")
    reservation2, status2 = service.reserve_stock("SKU001", 50, "key1")
    assert status2 == 200
    assert reservation1['id'] == reservation2['id']


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.reserve_stock("SKU001", 50, "key1")
    order = service.confirm_reservation(reservation['id'])
    assert order['reservation_id'] == reservation['id']


def test_confirm_reservation_expired(service, test_db):
    service.create_sku("SKU001", 100)
    reservation, _ = service.reserve_stock("SKU001", 50, "key1")

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    with test_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE reservations SET created_at = ? WHERE id = ?', (old_time, reservation['id']))
        conn.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation['id'])


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.reserve_stock("SKU001", 50, "key1")
    result = service.cancel_reservation(reservation['id'])
    assert result['status'] == 'CANCELLED'
