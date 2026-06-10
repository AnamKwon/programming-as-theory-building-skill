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
    service.create_sku("SKU-001", 100)
    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert on_hand == 100
    assert reserved == 0


def test_adjust_stock_positive(service):
    service.create_sku("SKU-001", 50)
    service.adjust_stock("SKU-001", 25)
    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert on_hand == 75


def test_adjust_stock_negative(service):
    service.create_sku("SKU-001", 100)
    service.adjust_stock("SKU-001", -30)
    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert on_hand == 70


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(ValueError, match="SKU .* not found"):
        service.adjust_stock("SKU-MISSING", 10)


def test_adjust_stock_below_reserved(service):
    service.create_sku("SKU-001", 100)
    service.create_reservation("SKU-001", 50, "idem-key-1")
    with pytest.raises(ValueError, match="Cannot reduce stock"):
        service.adjust_stock("SKU-001", -60)


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idem-key-1")
    assert res.sku == "SKU-001"
    assert res.units == 25
    assert res.state.value == "pending"
    assert res.expires_at > datetime.utcnow()

    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert on_hand == 100
    assert reserved == 25


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 50, "idem-key-1")


def test_create_reservation_sku_not_found(service):
    with pytest.raises(ValueError, match="SKU .* not found"):
        service.create_reservation("SKU-MISSING", 10, "idem-key-1")


def test_create_reservation_zero_units(service):
    service.create_sku("SKU-001", 100)
    with pytest.raises(ValueError, match="Units must be positive"):
        service.create_reservation("SKU-001", 0, "idem-key-1")


def test_create_reservation_idempotent_retry(service):
    service.create_sku("SKU-001", 100)
    res1 = service.create_reservation("SKU-001", 25, "idem-key-1")
    res2 = service.create_reservation("SKU-001", 25, "idem-key-1")
    assert res1.reservation_id == res2.reservation_id
    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert reserved == 25


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idem-key-1")
    order = service.confirm_reservation(res.reservation_id)
    assert order.sku == "SKU-001"
    assert order.units == 25

    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert on_hand == 100
    assert reserved == 0

    confirmed_res = service.get_reservation(res.reservation_id)
    assert confirmed_res.state.value == "confirmed"


def test_confirm_reservation_expired(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idem-key-1")

    # Manually expire the reservation using the shared connection
    conn = service.repo._get_connection()
    cursor = conn.cursor()
    past_time = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    cursor.execute(
        "UPDATE reservations SET expires_at = ? WHERE reservation_id = ?",
        (past_time, res.reservation_id),
    )
    conn.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res.reservation_id)


def test_confirm_reservation_not_found(service):
    with pytest.raises(ValueError, match="Reservation .* not found"):
        service.confirm_reservation("UNKNOWN-ID")


def test_cancel_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 25, "idem-key-1")
    service.cancel_reservation(res.reservation_id)

    on_hand, reserved = service.repo.get_sku("SKU-001")
    assert on_hand == 100
    assert reserved == 0

    cancelled_res = service.get_reservation(res.reservation_id)
    assert cancelled_res.state.value == "cancelled"


def test_cancel_reservation_not_found(service):
    with pytest.raises(ValueError, match="Reservation .* not found"):
        service.cancel_reservation("UNKNOWN-ID")


def test_get_orders_empty(service):
    orders, total = service.get_orders()
    assert orders == []
    assert total == 0


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 1000)
    for i in range(15):
        res = service.create_reservation("SKU-001", 10, f"idem-{i}")
        service.confirm_reservation(res.reservation_id)

    orders, total = service.get_orders(limit=10, offset=0)
    assert len(orders) == 10
    assert total == 15

    orders, total = service.get_orders(limit=10, offset=10)
    assert len(orders) == 5
    assert total == 15


def test_get_orders_invalid_limit(service):
    with pytest.raises(ValueError, match="Limit must be between 1 and 100"):
        service.get_orders(limit=0)

    with pytest.raises(ValueError, match="Limit must be between 1 and 100"):
        service.get_orders(limit=101)


def test_get_orders_invalid_offset(service):
    with pytest.raises(ValueError, match="Offset must be non-negative"):
        service.get_orders(offset=-1)
