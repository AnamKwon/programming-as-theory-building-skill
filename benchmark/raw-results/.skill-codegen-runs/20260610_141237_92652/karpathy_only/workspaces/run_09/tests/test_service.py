import pytest
import time
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def repository():
    return Repository(":memory:")


@pytest.fixture
def service(repository):
    return CommerceService(repository)


def test_create_sku(service):
    assert service.create_sku("SKU-001", 100) is True
    sku_record = service.repo.get_sku("SKU-001")
    assert sku_record is not None
    assert sku_record["available_stock"] == 100
    assert sku_record["reserved_stock"] == 0


def test_create_duplicate_sku(service):
    service.create_sku("SKU-001", 100)
    assert service.create_sku("SKU-001", 50) is False


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)

    result = service.adjust_stock("SKU-001", 50)
    assert result is not None
    assert result["available_stock"] == 150

    result = service.adjust_stock("SKU-001", -30)
    assert result is not None
    assert result["available_stock"] == 120


def test_adjust_stock_nonexistent_sku(service):
    result = service.adjust_stock("SKU-999", 10)
    assert result is None


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)

    response, status_code = service.create_reservation("SKU-001", 50, "key-1")
    assert status_code == 201
    assert response.sku == "SKU-001"
    assert response.quantity == 50
    assert response.status == "PENDING"

    sku_record = service.repo.get_sku("SKU-001")
    assert sku_record["available_stock"] == 50
    assert sku_record["reserved_stock"] == 50


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)

    response, status_code = service.create_reservation("SKU-001", 50, "key-1")
    assert status_code == 400
    assert response is None

    sku_record = service.repo.get_sku("SKU-001")
    assert sku_record["available_stock"] == 30
    assert sku_record["reserved_stock"] == 0


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)

    response1, status1 = service.create_reservation("SKU-001", 50, "key-1")
    assert status1 == 201

    sku_record = service.repo.get_sku("SKU-001")
    stock_after_first = sku_record["available_stock"]

    response2, status2 = service.create_reservation("SKU-001", 50, "key-1")
    assert status2 == 200
    assert response1.id == response2.id

    sku_record = service.repo.get_sku("SKU-001")
    assert sku_record["available_stock"] == stock_after_first


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    response, _ = service.create_reservation("SKU-001", 50, "key-1")
    reservation_id = response.id

    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 200
    assert result["reservation_id"] == reservation_id
    assert result["status"] == "CONFIRMED"
    assert "order_id" in result

    order = service.repo.repo.get_orders(page=1, size=10)[0][0]
    assert order["sku"] == "SKU-001"
    assert order["quantity"] == 50


def test_confirm_reservation_nonexistent(service):
    result, status_code = service.confirm_reservation(999)
    assert status_code == 404


def test_confirm_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    response, _ = service.create_reservation("SKU-001", 50, "key-1")
    reservation_id = response.id

    service.confirm_reservation(reservation_id)

    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 400


def test_confirm_reservation_expired(service):
    service.create_sku("SKU-001", 100)
    response, _ = service.create_reservation("SKU-001", 50, "key-1")
    reservation_id = response.id

    reservation = service.repo.get_reservation(reservation_id)
    old_created_at = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    service.repo._get_connection().execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_created_at, reservation_id),
    )
    service.repo._get_connection().commit()

    result, status_code = service.confirm_reservation(reservation_id)
    assert status_code == 400
    assert result["detail"] == "Reservation expired"

    reservation = service.repo.get_reservation(reservation_id)
    assert reservation["status"] == "EXPIRED"

    sku_record = service.repo.get_sku("SKU-001")
    assert sku_record["available_stock"] == 100
    assert sku_record["reserved_stock"] == 0


def test_cancel_reservation_success(service):
    service.create_sku("SKU-001", 100)
    response, _ = service.create_reservation("SKU-001", 50, "key-1")
    reservation_id = response.id

    sku_before = service.repo.get_sku("SKU-001")
    assert sku_before["available_stock"] == 50

    result, status_code = service.cancel_reservation(reservation_id)
    assert status_code == 200
    assert result["status"] == "CANCELLED"
    assert result["restored_stock"] == 100

    sku_after = service.repo.get_sku("SKU-001")
    assert sku_after["available_stock"] == 100
    assert sku_after["reserved_stock"] == 0


def test_cancel_reservation_not_pending(service):
    service.create_sku("SKU-001", 100)
    response, _ = service.create_reservation("SKU-001", 50, "key-1")
    reservation_id = response.id

    service.confirm_reservation(reservation_id)

    result, status_code = service.cancel_reservation(reservation_id)
    assert status_code == 400


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 1000)

    for i in range(25):
        response, _ = service.create_reservation("SKU-001", 10, f"key-{i}")
        service.confirm_reservation(response.id)

    orders, total, page = service.get_orders(page=1, size=10)
    assert len(orders) == 10
    assert total == 25
    assert page == 1

    orders2, total2, page2 = service.get_orders(page=2, size=10)
    assert len(orders2) == 10
    assert total2 == 25
    assert page2 == 2

    orders3, total3, page3 = service.get_orders(page=3, size=10)
    assert len(orders3) == 5
    assert total3 == 25
    assert page3 == 3
