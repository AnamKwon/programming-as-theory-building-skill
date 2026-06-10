import pytest
from datetime import datetime, timedelta
import time
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository(":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert "id" in result


def test_adjust_stock_increase(service):
    service.create_sku("SKU002", 50)
    result = service.adjust_stock("SKU002", 10)
    assert result["available_stock"] == 60


def test_adjust_stock_decrease(service):
    service.create_sku("SKU003", 50)
    result = service.adjust_stock("SKU003", -20)
    assert result["available_stock"] == 30


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU004", 100)
    result = service.create_reservation("SKU004", 30, "key001")
    assert result["status"] == "PENDING"
    assert result["quantity"] == 30
    assert "id" in result
    assert "created_at" in result


def test_create_reservation_deducts_stock(service):
    service.create_sku("SKU005", 100)
    service.create_reservation("SKU005", 30, "key002")

    sku = service.repo.get_sku_by_name("SKU005")
    assert sku["available_stock"] == 70


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU006", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU006", 50, "key003")


def test_create_reservation_idempotent(service):
    service.create_sku("SKU007", 100)
    res1 = service.create_reservation("SKU007", 25, "key004")
    res2 = service.create_reservation("SKU007", 25, "key004")

    assert res1["id"] == res2["id"]
    assert res1["status"] == res2["status"]

    sku = service.repo.get_sku_by_name("SKU007")
    assert sku["available_stock"] == 75


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU008", 100)
    res = service.create_reservation("SKU008", 30, "key005")
    res_id = res["id"]

    result = service.confirm_reservation(res_id)
    assert result["status"] == "CONFIRMED"
    assert "order_id" in result
    assert result["reservation_id"] == res_id


def test_confirm_non_pending_reservation(service):
    service.create_sku("SKU009", 100)
    res = service.create_reservation("SKU009", 30, "key006")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    with pytest.raises(ValueError, match="not pending"):
        service.confirm_reservation(res_id)


def test_cancel_reservation_restores_stock(service):
    service.create_sku("SKU010", 100)
    res = service.create_reservation("SKU010", 30, "key007")
    res_id = res["id"]

    sku_before = service.repo.get_sku_by_name("SKU010")
    assert sku_before["available_stock"] == 70

    service.cancel_reservation(res_id)

    sku_after = service.repo.get_sku_by_name("SKU010")
    assert sku_after["available_stock"] == 100


def test_cancel_non_pending_reservation(service):
    service.create_sku("SKU011", 100)
    res = service.create_reservation("SKU011", 30, "key008")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    with pytest.raises(ValueError, match="not pending"):
        service.cancel_reservation(res_id)


def test_expired_reservation_on_confirm(service):
    from datetime import datetime, timedelta

    service.create_sku("SKU012", 100)
    res = service.create_reservation("SKU012", 30, "key009")
    res_id = res["id"]

    sku_before = service.repo.get_sku_by_name("SKU012")
    assert sku_before["available_stock"] == 70

    conn = service.repo.get_connection()
    cursor = conn.cursor()
    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (old_time, res_id))
    conn.commit()
    service.repo._close_conn(conn)

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res_id)

    updated_res = service.repo.get_reservation_by_id(res_id)
    assert updated_res["status"] == "EXPIRED"

    sku_after = service.repo.get_sku_by_name("SKU012")
    assert sku_after["available_stock"] == 100


def test_get_orders(service):
    service.create_sku("SKU013", 100)
    res1 = service.create_reservation("SKU013", 10, "key010")
    res2 = service.create_reservation("SKU013", 20, "key011")

    service.confirm_reservation(res1["id"])
    service.confirm_reservation(res2["id"])

    result = service.get_orders(page=1, size=10)
    assert result["page"] == 1
    assert result["size"] == 10
    assert result["total"] == 2
    assert len(result["items"]) == 2


def test_get_orders_pagination(service):
    service.create_sku("SKU014", 1000)
    for i in range(15):
        res = service.create_reservation("SKU014", 10, f"key_page_{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert len(page1["items"]) == 10
    assert page1["total"] == 15

    page2 = service.get_orders(page=2, size=10)
    assert len(page2["items"]) == 5
    assert page2["total"] == 15
