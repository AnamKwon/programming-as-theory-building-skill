import os
import tempfile
import pytest
from datetime import datetime, timedelta

from commerce_service.repository import Database
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    db = Database(path)
    yield db
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def service(temp_db):
    return CommerceService(temp_db)


def test_create_sku(service):
    result = service.create_sku("WIDGET-001", "Premium Widget")
    assert result["id"] == 1
    assert result["sku"] == "WIDGET-001"
    assert result["name"] == "Premium Widget"


def test_adjust_stock(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    result = service.adjust_stock("WIDGET-001", 100)
    assert result["old_quantity"] == 0
    assert result["new_quantity"] == 100


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("NONEXISTENT", 100)


def test_create_reservation_happy_path(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    result = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    assert result["id"] == 1
    assert result["sku"] == "WIDGET-001"
    assert result["quantity"] == 10
    assert result["status"] == "pending"
    assert result["customer_id"] == "cust_123"
    assert result["idempotent"] is False


def test_create_reservation_insufficient_stock(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(
            sku="WIDGET-001",
            quantity=10,
            customer_id="cust_123",
            idempotency_key="key_1",
        )


def test_create_reservation_idempotency(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    first = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    second = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    assert first["id"] == second["id"]
    assert second["idempotent"] is True


def test_create_reservation_nonexistent_sku(service):
    with pytest.raises(ValueError, match="SKU not found"):
        service.create_reservation(
            sku="NONEXISTENT",
            quantity=10,
            customer_id="cust_123",
            idempotency_key="key_1",
        )


def test_confirm_reservation(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    reservation = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    confirmed = service.confirm_reservation(reservation["id"])

    assert confirmed["status"] == "confirmed"
    assert confirmed["order_id"] is not None


def test_confirm_reservation_expired(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    reservation = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    service.db.update_reservation_status(reservation["id"], "expired")

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation["id"])


def test_confirm_reservation_nonexistent(service):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_cancel_reservation(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    reservation = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    service.cancel_reservation(reservation["id"])

    result = service.db.get_reservation(reservation["id"])
    assert result["status"] == "cancelled"


def test_get_order(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    reservation = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    confirmed = service.confirm_reservation(reservation["id"])
    order = service.get_order(confirmed["order_id"])

    assert order["status"] == "confirmed"
    assert order["customer_id"] == "cust_123"
    assert len(order["items"]) == 1
    assert order["items"][0]["sku"] == "WIDGET-001"


def test_list_orders_pagination(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 500)

    for i in range(15):
        reservation = service.create_reservation(
            sku="WIDGET-001",
            quantity=10,
            customer_id="cust_123",
            idempotency_key=f"key_{i}",
        )
        service.confirm_reservation(reservation["id"])

    page1 = service.list_orders("cust_123", page=1, page_size=10)
    assert len(page1["orders"]) == 10
    assert page1["total"] == 15
    assert page1["page"] == 1

    page2 = service.list_orders("cust_123", page=2, page_size=10)
    assert len(page2["orders"]) == 5
    assert page2["page"] == 2


def test_cleanup_expired_reservations(service):
    service.create_sku("WIDGET-001", "Premium Widget")
    service.adjust_stock("WIDGET-001", 50)

    reservation = service.create_reservation(
        sku="WIDGET-001",
        quantity=10,
        customer_id="cust_123",
        idempotency_key="key_1",
    )

    now = datetime.utcnow()
    past = (now - timedelta(minutes=20)).isoformat()
    service.db.db_path

    conn = service.db._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET expires_at = ? WHERE id = ?",
        (past, reservation["id"]),
    )
    conn.commit()
    conn.close()

    count = service.cleanup_expired_reservations()
    assert count == 1

    expired = service.db.get_reservation(reservation["id"])
    assert expired["status"] == "expired"
