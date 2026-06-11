import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def service():
    repo = Repository()
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result is True


def test_create_sku_duplicate(service):
    service.create_sku("SKU001", 100)
    result = service.create_sku("SKU001", 50)
    assert result is False


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    updated = service.adjust_stock("SKU001", 10)
    assert updated == 110


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", 100)
    updated = service.adjust_stock("SKU001", -30)
    assert updated == 70


def test_adjust_stock_nonexistent(service):
    result = service.adjust_stock("NONEXISTENT", 10)
    assert result is None


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation, error = service.create_reservation("SKU001", 50, "idempotency-1")
    assert error is None
    assert reservation is not None
    assert reservation["status"] == "PENDING"
    assert reservation["quantity"] == 50
    assert service.repo.get_sku_stock("SKU001") == 50


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 50)
    reservation, error = service.create_reservation("SKU001", 100, "idempotency-1")
    assert error == "Insufficient stock"
    assert reservation is None
    assert service.repo.get_sku_stock("SKU001") == 50


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    reservation1, error1 = service.create_reservation("SKU001", 50, "idempotency-1")
    stock_after_first = service.repo.get_sku_stock("SKU001")

    reservation2, error2 = service.create_reservation("SKU001", 50, "idempotency-1")
    stock_after_second = service.repo.get_sku_stock("SKU001")

    assert error1 is None
    assert error2 is None
    assert reservation1["id"] == reservation2["id"]
    assert stock_after_first == stock_after_second
    assert stock_after_first == 50


def test_create_reservation_nonexistent_sku(service):
    reservation, error = service.create_reservation("NONEXISTENT", 50, "idempotency-1")
    assert error == "SKU not found"
    assert reservation is None


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-1")
    reservation_id = reservation["id"]

    order, error = service.confirm_reservation(reservation_id)
    assert error is None
    assert order is not None
    assert order["reservation_id"] == reservation_id

    updated_reservation = service.repo.get_reservation(reservation_id)
    assert updated_reservation["status"] == "CONFIRMED"


def test_confirm_reservation_nonexistent(service):
    order, error = service.confirm_reservation(999)
    assert error == "Reservation not found"
    assert order is None


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-1")
    reservation_id = reservation["id"]

    service.confirm_reservation(reservation_id)
    order, error = service.confirm_reservation(reservation_id)
    assert error == "Reservation is not pending"
    assert order is None


def test_confirm_reservation_expired(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-1")
    reservation_id = reservation["id"]

    repo = service.repo
    repo.update_reservation_status(reservation_id, "PENDING")
    old_time = (datetime.utcnow() - timedelta(seconds=400)).isoformat()
    cursor = repo.conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    repo.conn.commit()

    stock_before = repo.get_sku_stock("SKU001")
    order, error = service.confirm_reservation(reservation_id)
    stock_after = repo.get_sku_stock("SKU001")

    assert error == "Reservation expired"
    assert order is None
    updated_reservation = repo.get_reservation(reservation_id)
    assert updated_reservation["status"] == "EXPIRED"
    assert stock_after == stock_before + 50


def test_cancel_reservation_success(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-1")
    reservation_id = reservation["id"]

    stock_before = service.repo.get_sku_stock("SKU001")
    cancelled, error = service.cancel_reservation(reservation_id)
    stock_after = service.repo.get_sku_stock("SKU001")

    assert error is None
    assert cancelled["status"] == "CANCELLED"
    assert stock_after == stock_before + 50

    updated_reservation = service.repo.get_reservation(reservation_id)
    assert updated_reservation["status"] == "CANCELLED"


def test_cancel_reservation_nonexistent(service):
    cancelled, error = service.cancel_reservation(999)
    assert error == "Reservation not found"
    assert cancelled is None


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU001", 100)
    reservation, _ = service.create_reservation("SKU001", 50, "idempotency-1")
    reservation_id = reservation["id"]

    service.confirm_reservation(reservation_id)
    cancelled, error = service.cancel_reservation(reservation_id)
    assert error == "Reservation is not pending"
    assert cancelled is None


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(25):
        reservation, _ = service.create_reservation("SKU001", 1, f"idempotency-{i}")
        service.confirm_reservation(reservation["id"])

    page1, total1 = service.get_orders(page=1, size=10)
    page2, total2 = service.get_orders(page=2, size=10)
    page3, total3 = service.get_orders(page=3, size=10)

    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5
    assert total1 == 25
    assert total2 == 25
    assert total3 == 25
