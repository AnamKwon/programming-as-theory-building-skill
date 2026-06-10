import tempfile
from datetime import datetime, timedelta

import pytest

from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db_instance = Database(db_path)
    yield db_instance


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    assert sku_dict["sku"] == "SKU-001"
    assert sku_dict["name"] == "Test Product"
    assert sku_dict["stock"] == 100
    assert sku_dict["reserved"] == 0


def test_create_duplicate_sku_fails(service):
    service.create_sku("SKU-001", "Test Product", 100)
    with pytest.raises(Exception) as exc_info:
        service.create_sku("SKU-001", "Another Product", 50)
    assert "already exists" in str(exc_info.value)


def test_adjust_stock(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    adjusted = service.adjust_stock(sku_id, 25)
    assert adjusted["stock"] == 125

    adjusted = service.adjust_stock(sku_id, -50)
    assert adjusted["stock"] == 75


def test_adjust_stock_to_negative_fails(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    with pytest.raises(Exception) as exc_info:
        service.adjust_stock(sku_id, -150)
    assert "negative stock" in str(exc_info.value)


def test_create_reservation(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    res_dict = service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )
    assert res_dict["order_id"] == "ORDER-001"
    assert res_dict["sku_id"] == sku_id
    assert res_dict["quantity"] == 50
    assert res_dict["status"] == "pending"


def test_insufficient_stock_fails(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    with pytest.raises(Exception) as exc_info:
        service.create_reservation(
            "ORDER-001",
            sku_id,
            150,
            "IDEMPOTENCY-001",
        )
    assert "Insufficient stock" in str(exc_info.value)


def test_idempotent_reservation_retry(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    res1 = service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )

    res2 = service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )

    assert res1["id"] == res2["id"]


def test_idempotency_key_collision_fails(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )

    with pytest.raises(Exception) as exc_info:
        service.create_reservation(
            "ORDER-002",
            sku_id,
            25,
            "IDEMPOTENCY-001",
        )
    assert "Idempotency key already used" in str(exc_info.value)


def test_confirm_reservation(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    res_dict = service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )
    res_id = res_dict["id"]

    confirmed = service.confirm_reservation(res_id)
    assert confirmed["status"] == "confirmed"


def test_confirm_expired_reservation_fails(service, db):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    expires_at = datetime.utcnow() - timedelta(minutes=1)
    res_id = db.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
        expires_at,
    )
    db.reserve_stock(sku_id, 50)

    with pytest.raises(Exception) as exc_info:
        service.confirm_reservation(res_id)
    assert "expired" in str(exc_info.value)


def test_cancel_reservation(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    res_dict = service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )
    res_id = res_dict["id"]

    cancelled = service.cancel_reservation(res_id)
    assert cancelled["status"] == "cancelled"


def test_cancel_confirmed_reservation_releases_stock(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    res_dict = service.create_reservation(
        "ORDER-001",
        sku_id,
        50,
        "IDEMPOTENCY-001",
    )
    res_id = res_dict["id"]

    service.confirm_reservation(res_id)

    service.cancel_reservation(res_id)

    updated_sku = service.db.get_sku(sku_id)
    assert updated_sku["reserved"] == 0


def test_get_orders_pagination(service):
    sku_dict = service.create_sku("SKU-001", "Test Product", 100)
    sku_id = sku_dict["id"]

    for i in range(10):
        service.create_reservation(
            f"ORDER-{i:03d}",
            sku_id,
            10,
            f"IDEMPOTENCY-{i:03d}",
        )

    result = service.get_orders(limit=5, offset=0)
    assert len(result["items"]) == 5
    assert result["total"] == 10
    assert result["limit"] == 5
    assert result["offset"] == 0

    result = service.get_orders(limit=5, offset=5)
    assert len(result["items"]) == 5
    assert result["offset"] == 5
