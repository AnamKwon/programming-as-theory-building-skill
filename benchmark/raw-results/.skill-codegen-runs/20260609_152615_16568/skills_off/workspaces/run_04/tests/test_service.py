import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import ReservationStatus


@pytest.fixture
def repo():
    return Repository()


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    sku = service.create_sku("PROD-001")
    assert sku["id"] is not None
    assert sku["name"] == "PROD-001"


def test_create_duplicate_sku_fails(service):
    service.create_sku("PROD-001")
    with pytest.raises(HTTPException) as exc_info:
        service.create_sku("PROD-001")
    assert exc_info.value.status_code == 409


def test_adjust_stock(service):
    sku = service.create_sku("PROD-001")
    stock = service.adjust_stock(sku["id"], 100)
    assert stock["quantity"] == 100


def test_adjust_stock_nonexistent_sku_fails(service):
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(999, 10)
    assert exc_info.value.status_code == 404


def test_adjust_stock_negative_fails(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 10)
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(sku["id"], -20)
    assert exc_info.value.status_code == 400


def test_create_reservation_success(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    reservation = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    assert reservation["id"] is not None
    assert reservation["status"] == ReservationStatus.RESERVED
    assert reservation["quantity"] == 10


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 5)

    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(sku["id"], 10, "idempotency-1", ttl_seconds=3600)
    assert exc_info.value.status_code == 409
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_idempotent(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    res1 = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    res2 = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    assert res1["id"] == res2["id"]


def test_create_reservation_reuse_cancelled_key_fails(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    res1 = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    service.cancel_reservation(res1["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(sku["id"], 10, "idempotency-1", ttl_seconds=3600)
    assert exc_info.value.status_code == 409


def test_confirm_reservation_success(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    reservation = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    confirmed = service.confirm_reservation(reservation["id"])
    assert confirmed["status"] == ReservationStatus.CONFIRMED

    # Verify stock was deducted
    stock = service.repo.get_stock(sku["id"])
    assert stock["quantity"] == 90


def test_confirm_reservation_expired_fails(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    # Create reservation with 0 TTL to immediately expire it
    reservation = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=0
    )

    # Force the reservation to be expired
    repo = service.repo
    repo.execute = lambda sql, args: None
    now = datetime.utcnow().isoformat()
    with repo._get_connection() as conn:
        conn.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (now, reservation["id"]),
        )

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert exc_info.value.status_code == 410


def test_confirm_non_reserved_reservation_fails(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    reservation = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    service.confirm_reservation(reservation["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation["id"])
    assert exc_info.value.status_code == 409


def test_cancel_reservation_success(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    reservation = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    cancelled = service.cancel_reservation(reservation["id"])
    assert cancelled["status"] == ReservationStatus.CANCELLED


def test_cancel_non_reserved_reservation_fails(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 100)

    reservation = service.create_reservation(
        sku["id"], 10, "idempotency-1", ttl_seconds=3600
    )
    service.confirm_reservation(reservation["id"])

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation["id"])
    assert exc_info.value.status_code == 409


def test_list_orders_pagination(service):
    sku = service.create_sku("PROD-001")
    service.adjust_stock(sku["id"], 1000)

    # Create and confirm multiple reservations
    for i in range(5):
        res = service.create_reservation(
            sku["id"], 10, f"idempotency-{i}", ttl_seconds=3600
        )
        service.confirm_reservation(res["id"])

    # Test pagination
    orders, next_cursor = service.list_orders(limit=2, cursor=0)
    assert len(orders) == 2
    assert next_cursor is not None

    # Get next page
    next_orders, final_cursor = service.list_orders(limit=2, cursor=next_cursor)
    assert len(next_orders) == 2
