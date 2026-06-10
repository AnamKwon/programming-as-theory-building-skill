import pytest
import tempfile
from datetime import datetime, timedelta

from commerce_service.repository import Database
from commerce_service.service import ServiceLayer, ValidationError


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path=db_path)
    yield db
    import os
    os.unlink(db_path)


@pytest.fixture
def service(temp_db):
    return ServiceLayer(temp_db)


def test_create_sku(service):
    sku = service.create_sku("SKU-001", 100)
    assert sku["sku_code"] == "SKU-001"
    assert sku["stock_qty"] == 100


def test_create_duplicate_sku(service):
    service.create_sku("SKU-001", 100)
    with pytest.raises(ValidationError, match="already exists"):
        service.create_sku("SKU-001", 50)


def test_adjust_stock_positive(service):
    sku = service.create_sku("SKU-001", 100)
    adjusted = service.adjust_stock(sku["id"], 50)
    assert adjusted["stock_qty"] == 150


def test_adjust_stock_negative(service):
    sku = service.create_sku("SKU-001", 100)
    adjusted = service.adjust_stock(sku["id"], -30)
    assert adjusted["stock_qty"] == 70


def test_adjust_stock_below_zero(service):
    sku = service.create_sku("SKU-001", 100)
    with pytest.raises(ValidationError, match="negative inventory"):
        service.adjust_stock(sku["id"], -150)


def test_adjust_nonexistent_sku(service):
    with pytest.raises(ValidationError, match="not found"):
        service.adjust_stock(999, 10)


def test_create_reservation_success(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    assert res["sku_code"] == "SKU-001"
    assert res["qty"] == 25
    assert res["status"] == "pending"


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 50)
    with pytest.raises(ValidationError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 100, "idempotency-1")


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(ValidationError, match="not found"):
        service.create_reservation("SKU-999", 10, "idempotency-1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    res1 = service.create_reservation("SKU-001", 25, "idempotency-1")
    res2 = service.create_reservation("SKU-001", 30, "idempotency-1")
    assert res1["id"] == res2["id"]
    assert res2["qty"] == 25


def test_confirm_reservation_success(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    confirmed_res, order = service.confirm_reservation(res["id"], "idempotency-1")
    assert confirmed_res["status"] == "confirmed"
    assert order["status"] == "created"


def test_confirm_reservation_idempotency_key_mismatch(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    with pytest.raises(ValidationError, match="Idempotency key mismatch"):
        service.confirm_reservation(res["id"], "wrong-key")


def test_confirm_already_confirmed_reservation(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    service.confirm_reservation(res["id"], "idempotency-1")
    _, order = service.confirm_reservation(res["id"], "idempotency-1")
    assert order["id"] is not None


def test_confirm_expired_reservation(service, temp_db):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")

    with temp_db.get_connection() as conn:
        past = (datetime.utcnow() - timedelta(minutes=20)).isoformat()
        conn.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past, res["id"]),
        )
        conn.commit()

    with pytest.raises(ValidationError, match="expired"):
        service.confirm_reservation(res["id"], "idempotency-1")


def test_cancel_reservation_success(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    cancelled = service.cancel_reservation(res["id"])
    assert cancelled["status"] == "cancelled"


def test_cancel_confirmed_reservation(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    service.confirm_reservation(res["id"], "idempotency-1")
    with pytest.raises(ValidationError, match="Cannot cancel"):
        service.cancel_reservation(res["id"])


def test_get_order_success(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idempotency-1")
    _, order = service.confirm_reservation(res["id"], "idempotency-1")
    retrieved = service.get_order(order["id"])
    assert retrieved["id"] == order["id"]


def test_get_nonexistent_order(service):
    with pytest.raises(ValidationError, match="not found"):
        service.get_order(999)


def test_list_orders_pagination(service):
    service.create_sku("SKU-001", 1000)
    for i in range(5):
        res = service.create_reservation("SKU-001", 10, f"idempotency-{i}")
        service.confirm_reservation(res["id"], f"idempotency-{i}")

    orders, total = service.list_orders(limit=2, offset=0)
    assert len(orders) == 2
    assert total == 5

    orders2, _ = service.list_orders(limit=2, offset=2)
    assert len(orders2) == 2
    assert orders[0]["id"] != orders2[0]["id"]
