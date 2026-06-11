import pytest
import os
import tempfile
import time
from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    db_instance = Database(path)
    yield db_instance
    try:
        os.remove(path)
    except:
        pass


@pytest.fixture
def service(temp_db):
    return CommerceService(temp_db)


def test_create_sku(service, temp_db):
    service.create_sku("SKU-001", 100)
    assert temp_db.get_sku_stock("SKU-001") == 100


def test_adjust_stock_increase(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", 50)
    assert result["stock"] == 150
    assert result["sku"] == "SKU-001"


def test_adjust_stock_decrease(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", -30)
    assert result["stock"] == 70


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idem-001")

    assert reservation["status"] == "PENDING"
    assert reservation["sku"] == "SKU-001"
    assert reservation["quantity"] == 10
    assert reservation["idempotency_key"] == "idem-001"
    assert temp_db.get_sku_stock("SKU-001") == 90


def test_create_reservation_insufficient_stock(service, temp_db):
    temp_db.create_sku("SKU-001", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 100, "idem-002")

    assert temp_db.get_sku_stock("SKU-001") == 50


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.create_reservation("NONEXISTENT", 10, "idem-003")


def test_idempotent_reservation(service, temp_db):
    temp_db.create_sku("SKU-001", 100)

    first = service.create_reservation("SKU-001", 10, "idem-004")
    first_stock = temp_db.get_sku_stock("SKU-001")

    second = service.create_reservation("SKU-001", 10, "idem-004")
    second_stock = temp_db.get_sku_stock("SKU-001")

    assert first["id"] == second["id"]
    assert first_stock == second_stock == 90


def test_confirm_reservation_success(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idem-005")

    order = service.confirm_reservation(reservation["id"])

    assert order["reservation_id"] == reservation["id"]
    updated = temp_db.get_reservation(reservation["id"])
    assert updated["status"] == "CONFIRMED"


def test_confirm_nonexistent_reservation(service):
    with pytest.raises(ValueError, match="Reservation not found"):
        service.confirm_reservation(999)


def test_confirm_non_pending_reservation(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idem-006")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="Cannot confirm reservation with status"):
        service.confirm_reservation(reservation["id"])


def test_expired_reservation(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idem-007")
    assert temp_db.get_sku_stock("SKU-001") == 90

    time.sleep(301)

    with pytest.raises(ValueError, match="Reservation expired"):
        service.confirm_reservation(reservation["id"])

    updated = temp_db.get_reservation(reservation["id"])
    assert updated["status"] == "EXPIRED"
    assert temp_db.get_sku_stock("SKU-001") == 100


def test_cancel_reservation_success(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idem-008")
    assert temp_db.get_sku_stock("SKU-001") == 90

    result = service.cancel_reservation(reservation["id"])
    assert result["status"] == "CANCELLED"
    assert temp_db.get_sku_stock("SKU-001") == 100


def test_cancel_nonexistent_reservation(service):
    with pytest.raises(ValueError, match="Reservation not found"):
        service.cancel_reservation(999)


def test_cancel_non_pending_reservation(service, temp_db):
    temp_db.create_sku("SKU-001", 100)
    reservation = service.create_reservation("SKU-001", 10, "idem-009")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="Cannot cancel reservation with status"):
        service.cancel_reservation(reservation["id"])


def test_get_orders_pagination(service, temp_db):
    temp_db.create_sku("SKU-001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU-001", 1, f"idem-pag-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert page1["page"] == 1
    assert page1["size"] == 10
    assert len(page1["items"]) == 10
    assert page1["total"] == 25

    page2 = service.get_orders(page=2, size=10)
    assert page2["page"] == 2
    assert len(page2["items"]) == 10

    page3 = service.get_orders(page=3, size=10)
    assert len(page3["items"]) == 5
