import pytest
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
import time


@pytest.fixture
def repo():
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result is True


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    new_stock = service.adjust_stock("SKU001", -20)
    assert new_stock == 80


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", 100)
    reservation, status = service.create_reservation("SKU001", 20, "idempotency-key-1")
    assert status == "created"
    assert reservation is not None
    assert reservation['sku'] == "SKU001"
    assert reservation['quantity'] == 20
    assert reservation['status'] == "PENDING"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 50)
    reservation, status = service.create_reservation("SKU001", 100, "idempotency-key-1")
    assert status == "insufficient_stock"
    assert reservation is None


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)

    first_res, first_status = service.create_reservation("SKU001", 20, "idempotency-key-1")
    assert first_status == "created"
    first_id = first_res['id']

    second_res, second_status = service.create_reservation("SKU001", 20, "idempotency-key-1")
    assert second_status == "idempotent"
    assert second_res['id'] == first_id

    sku = service.repo.get_sku("SKU001")
    assert sku['available_stock'] == 80


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-key-1")

    order, status = service.confirm_reservation(reservation['id'])
    assert status == "confirmed"
    assert order is not None
    assert order['reservation_id'] == reservation['id']


def test_confirm_reservation_expired(service):
    service.create_sku("SKU001", 100)

    repo = service.repo
    from datetime import datetime, timezone, timedelta
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()

    conn = repo._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at) VALUES (?, ?, ?, ?, ?)",
        ("SKU001", 20, "idempotency-key-1", "PENDING", old_time)
    )
    conn.commit()
    res_id = cursor.lastrowid
    conn.close()

    repo.deduct_stock("SKU001", 20)

    order, status = service.confirm_reservation(res_id)
    assert status == "expired"
    assert order is None

    sku = repo.get_sku("SKU001")
    assert sku['available_stock'] == 100


def test_confirm_reservation_invalid_state(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-key-1")

    service.confirm_reservation(reservation['id'])

    order, status = service.confirm_reservation(reservation['id'])
    assert status == "invalid_state"
    assert order is None


def test_cancel_reservation(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 20, "idempotency-key-1")

    sku_before = service.repo.get_sku("SKU001")
    assert sku_before['available_stock'] == 80

    result, status = service.cancel_reservation(reservation['id'])
    assert status == "cancelled"

    sku_after = service.repo.get_sku("SKU001")
    assert sku_after['available_stock'] == 100


def test_get_orders(service):
    service.create_sku("SKU001", 100)

    for i in range(15):
        res, _ = service.create_reservation("SKU001", 1, f"idempotency-key-{i}")
        service.confirm_reservation(res['id'])

    orders, total = service.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 15

    orders_page2, _ = service.get_orders(page=2, size=10)
    assert len(orders_page2) == 5


def test_stock_deduction_on_reservation(service):
    service.create_sku("SKU001", 100)

    sku_initial = service.repo.get_sku("SKU001")
    assert sku_initial['available_stock'] == 100

    service.create_reservation("SKU001", 30, "idempotency-key-1")

    sku_after = service.repo.get_sku("SKU001")
    assert sku_after['available_stock'] == 70
