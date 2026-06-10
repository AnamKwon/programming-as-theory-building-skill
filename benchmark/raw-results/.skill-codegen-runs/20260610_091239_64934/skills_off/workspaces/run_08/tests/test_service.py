import pytest
import tempfile
import os
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield f"sqlite:///{db_path}"


@pytest.fixture
def service(temp_db):
    repo = Repository(db_url=temp_db)
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", "Widget", 100)
    assert result["sku_id"] == "SKU001"
    assert result["name"] == "Widget"
    assert result["current_stock"] == 100


def test_create_duplicate_sku(service):
    service.create_sku("SKU001", "Widget", 100)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("SKU001", "Another Widget", 50)


def test_adjust_stock(service):
    service.create_sku("SKU001", "Widget", 100)
    result = service.adjust_stock("SKU001", -10)
    assert result["current_stock"] == 90

    result = service.adjust_stock("SKU001", 20)
    assert result["current_stock"] == 110


def test_adjust_stock_below_zero(service):
    service.create_sku("SKU001", "Widget", 100)
    with pytest.raises(ValueError, match="cannot be negative"):
        service.adjust_stock("SKU001", -150)


def test_adjust_nonexistent_sku(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_reserve_stock(service):
    service.create_sku("SKU001", "Widget", 100)
    result = service.reserve_stock("SKU001", 10, "idempotency-1")

    assert result["reservation_id"]
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 10
    assert result["status"] == "created"
    assert result["expires_at"] > datetime.utcnow()


def test_reserve_insufficient_stock(service):
    service.create_sku("SKU001", "Widget", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.reserve_stock("SKU001", 20, "idempotency-1")


def test_reserve_nonexistent_sku(service):
    with pytest.raises(ValueError, match="not found"):
        service.reserve_stock("NONEXISTENT", 10, "idempotency-1")


def test_idempotent_reservation(service):
    service.create_sku("SKU001", "Widget", 100)

    result1 = service.reserve_stock("SKU001", 10, "idempotency-1")
    result2 = service.reserve_stock("SKU001", 10, "idempotency-1")

    assert result1["reservation_id"] == result2["reservation_id"]

    # Check stock was only decremented once
    sku_stock = service.repo.get_sku("SKU001")
    assert sku_stock["current_stock"] == 90


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Widget", 100)
    res = service.reserve_stock("SKU001", 10, "idempotency-1")

    order = service.confirm_reservation(res["reservation_id"])
    assert order["order_id"]
    assert order["status"] == "pending"
    assert order["sku_id"] == "SKU001"
    assert order["quantity"] == 10


def test_confirm_already_confirmed(service):
    service.create_sku("SKU001", "Widget", 100)
    res = service.reserve_stock("SKU001", 10, "idempotency-1")

    service.confirm_reservation(res["reservation_id"])

    with pytest.raises(ValueError, match="already confirmed"):
        service.confirm_reservation(res["reservation_id"])


def test_confirm_nonexistent_reservation(service):
    with pytest.raises(ValueError, match="not found"):
        service.confirm_reservation("nonexistent-id")


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Widget", 100)
    res = service.reserve_stock("SKU001", 10, "idempotency-1")

    # Verify stock was decremented
    assert service.repo.get_sku("SKU001")["current_stock"] == 90

    result = service.cancel_reservation(res["reservation_id"])
    assert result["status"] == "cancelled"

    # Verify stock was restored
    assert service.repo.get_sku("SKU001")["current_stock"] == 100


def test_cancel_already_confirmed_reservation(service):
    service.create_sku("SKU001", "Widget", 100)
    res = service.reserve_stock("SKU001", 10, "idempotency-1")
    service.confirm_reservation(res["reservation_id"])

    with pytest.raises(ValueError, match="Cannot cancel confirmed"):
        service.cancel_reservation(res["reservation_id"])


def test_list_orders(service):
    service.create_sku("SKU001", "Widget", 100)
    service.create_sku("SKU002", "Gadget", 50)

    res1 = service.reserve_stock("SKU001", 10, "idempotency-1")
    res2 = service.reserve_stock("SKU002", 5, "idempotency-2")

    service.confirm_reservation(res1["reservation_id"])
    service.confirm_reservation(res2["reservation_id"])

    result = service.list_orders(limit=10, offset=0)

    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["limit"] == 10
    assert result["offset"] == 0
    assert result["items"][0]["sku_id"] in ["SKU001", "SKU002"]


def test_list_orders_pagination(service):
    service.create_sku("SKU001", "Widget", 100)

    for i in range(5):
        res = service.reserve_stock("SKU001", 1, f"idempotency-{i}")
        service.confirm_reservation(res["reservation_id"])

    result1 = service.list_orders(limit=2, offset=0)
    assert len(result1["items"]) == 2
    assert result1["total"] == 5

    result2 = service.list_orders(limit=2, offset=2)
    assert len(result2["items"]) == 2

    result3 = service.list_orders(limit=2, offset=4)
    assert len(result3["items"]) == 1
