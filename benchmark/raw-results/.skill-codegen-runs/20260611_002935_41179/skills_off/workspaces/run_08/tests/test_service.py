import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository()


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku"] == "SKU001"
    assert result["available_stock"] == 100
    assert result["reserved_stock"] == 0


def test_adjust_stock(service):
    service.create_sku("SKU001", 100)
    result = service.adjust_stock("SKU001", -50)
    assert result["available_stock"] == 50
    assert result["reserved_stock"] == 0

    result = service.adjust_stock("SKU001", 30)
    assert result["available_stock"] == 80


def test_create_reservation_happy_path(service):
    service.create_sku("SKU001", 100)
    result = service.create_reservation("SKU001", 50, "key-1")
    assert result["id"] > 0
    assert result["status"] == "PENDING"
    assert result["quantity"] == 50


def test_insufficient_stock(service):
    service.create_sku("SKU001", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 100, "key-1")


def test_idempotency_key(service):
    service.create_sku("SKU001", 100)
    result1 = service.create_reservation("SKU001", 50, "key-1")
    result2 = service.create_reservation("SKU001", 50, "key-1")

    assert result1["id"] == result2["id"]
    assert result1["created_at"] == result2["created_at"]


def test_confirm_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key-1")
    order = service.confirm_reservation(res["id"])

    assert order["id"] > 0
    assert order["sku"] == "SKU001"
    assert order["quantity"] == 50


def test_reservation_expiration(service, repo):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key-1")

    # Manually set created_at to past
    conn = repo._get_connection()
    cursor = conn.cursor()
    old_time = (datetime.utcnow() - timedelta(seconds=310)).isoformat()
    cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (old_time, res["id"]))
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res["id"])

    # Verify stock was restored
    sku = repo.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 100
    assert sku["reserved_stock"] == 0


def test_cancel_reservation(service, repo):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key-1")

    service.cancel_reservation(res["id"])

    sku = repo.get_sku_by_name("SKU001")
    assert sku["available_stock"] == 100
    assert sku["reserved_stock"] == 0


def test_confirm_non_pending_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key-1")
    service.confirm_reservation(res["id"])

    with pytest.raises(ValueError, match="not PENDING"):
        service.confirm_reservation(res["id"])


def test_cancel_non_pending_reservation(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "key-1")
    service.confirm_reservation(res["id"])

    with pytest.raises(ValueError, match="not PENDING"):
        service.cancel_reservation(res["id"])


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(15):
        res = service.create_reservation("SKU001", 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    orders, total = service.get_orders(1, 10)
    assert len(orders) == 10
    assert total == 15

    orders_page2, total = service.get_orders(2, 10)
    assert len(orders_page2) == 5
    assert total == 15
