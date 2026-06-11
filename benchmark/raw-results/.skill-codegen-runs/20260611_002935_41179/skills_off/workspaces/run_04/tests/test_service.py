import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("TEST-SKU", 100)
    assert result["sku"] == "TEST-SKU"
    assert result["available_stock"] == 100
    assert result["id"] is not None


def test_adjust_stock_positive(service):
    service.create_sku("TEST-SKU", 100)
    result = service.adjust_stock("TEST-SKU", 50)
    assert result["available_stock"] == 150


def test_adjust_stock_negative(service):
    service.create_sku("TEST-SKU", 100)
    result = service.adjust_stock("TEST-SKU", -30)
    assert result["available_stock"] == 70


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    service.create_sku("TEST-SKU", 100)
    result = service.create_reservation("TEST-SKU", 50, "key-1")

    assert result["id"] is not None
    assert result["sku"] == "TEST-SKU"
    assert result["quantity"] == 50
    assert result["status"] == "PENDING"
    assert result["idempotency_key"] == "key-1"

    sku_data = service.repo.get_sku_by_name("TEST-SKU")
    assert sku_data["available_stock"] == 50


def test_create_reservation_insufficient_stock(service):
    service.create_sku("TEST-SKU", 30)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("TEST-SKU", 50, "key-1")


def test_create_reservation_idempotency(service):
    service.create_sku("TEST-SKU", 100)
    result1 = service.create_reservation("TEST-SKU", 50, "key-1")
    result2 = service.create_reservation("TEST-SKU", 50, "key-1")

    assert result1["id"] == result2["id"]
    assert result1["quantity"] == result2["quantity"]

    sku_data = service.repo.get_sku_by_name("TEST-SKU")
    assert sku_data["available_stock"] == 50


def test_confirm_reservation_success(service):
    service.create_sku("TEST-SKU", 100)
    reservation = service.create_reservation("TEST-SKU", 50, "key-1")

    result = service.confirm_reservation(reservation["id"])
    assert result["reservation_id"] == reservation["id"]
    assert result["order"]["id"] is not None

    updated_reservation = service.repo.get_reservation_by_id(reservation["id"])
    assert updated_reservation["status"] == "CONFIRMED"


def test_confirm_reservation_not_pending(service):
    service.create_sku("TEST-SKU", 100)
    reservation = service.create_reservation("TEST-SKU", 50, "key-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="not in PENDING"):
        service.confirm_reservation(reservation["id"])


def test_confirm_reservation_expired(service, repo):
    service.create_sku("TEST-SKU", 100)
    reservation = service.create_reservation("TEST-SKU", 50, "key-1")

    old_time = (datetime.utcnow() - timedelta(seconds=310)).isoformat()
    cursor = repo._get_connection().cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation["id"])
    )
    cursor.connection.commit()
    cursor.connection.close()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation["id"])

    updated_reservation = repo.get_reservation_by_id(reservation["id"])
    assert updated_reservation["status"] == "EXPIRED"

    sku_data = repo.get_sku_by_name("TEST-SKU")
    assert sku_data["available_stock"] == 100


def test_cancel_reservation_success(service):
    service.create_sku("TEST-SKU", 100)
    reservation = service.create_reservation("TEST-SKU", 50, "key-1")

    sku_before = service.repo.get_sku_by_name("TEST-SKU")
    assert sku_before["available_stock"] == 50

    result = service.cancel_reservation(reservation["id"])
    assert result["reservation_id"] == reservation["id"]
    assert result["status"] == "CANCELLED"

    updated_reservation = service.repo.get_reservation_by_id(reservation["id"])
    assert updated_reservation["status"] == "CANCELLED"

    sku_after = service.repo.get_sku_by_name("TEST-SKU")
    assert sku_after["available_stock"] == 100


def test_cancel_reservation_not_pending(service):
    service.create_sku("TEST-SKU", 100)
    reservation = service.create_reservation("TEST-SKU", 50, "key-1")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ValueError, match="not in PENDING"):
        service.cancel_reservation(reservation["id"])


def test_list_orders_pagination(service):
    service.create_sku("TEST-SKU", 500)

    for i in range(25):
        res = service.create_reservation("TEST-SKU", 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.list_orders(1, 10)
    assert len(page1["orders"]) == 10
    assert page1["total"] == 25
    assert page1["page"] == 1
    assert page1["size"] == 10

    page2 = service.list_orders(2, 10)
    assert len(page2["orders"]) == 10
    assert page2["total"] == 25
    assert page2["page"] == 2

    page3 = service.list_orders(3, 10)
    assert len(page3["orders"]) == 5
    assert page3["total"] == 25


def test_happy_path_workflow(service):
    service.create_sku("TEST-SKU", 100)

    reservation = service.create_reservation("TEST-SKU", 50, "key-1")
    assert reservation["status"] == "PENDING"

    confirm_result = service.confirm_reservation(reservation["id"])
    assert "order" in confirm_result

    orders = service.list_orders(1, 10)
    assert len(orders["orders"]) == 1
    assert orders["orders"][0]["reservation_id"] == reservation["id"]
