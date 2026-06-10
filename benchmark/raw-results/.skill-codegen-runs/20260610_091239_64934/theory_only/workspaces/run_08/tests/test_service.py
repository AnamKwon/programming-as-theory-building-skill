import pytest
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


@pytest.fixture
def db(repo):
    return repo.get_session()


def test_create_sku(service, db):
    result = service.create_sku(db, "PROD-001", "Widget")
    assert result["sku_id"] == "PROD-001"
    assert result["name"] == "Widget"


def test_get_sku(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    result = service.get_sku(db, "PROD-001")
    assert result["sku_id"] == "PROD-001"
    assert result["name"] == "Widget"


def test_get_nonexistent_sku(service, db):
    with pytest.raises(SKUNotFoundError):
        service.get_sku(db, "NONEXISTENT")


def test_adjust_stock_positive(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    result = service.adjust_stock(db, "PROD-001", 100)
    assert result["available"] == 100
    assert result["reserved"] == 0


def test_adjust_stock_negative_insufficient(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 10)
    with pytest.raises(InsufficientStockError):
        service.adjust_stock(db, "PROD-001", -20)


def test_get_stock(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 50)
    result = service.get_stock(db, "PROD-001")
    assert result["available"] == 50
    assert result["reserved"] == 0


def test_create_reservation_happy_path(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    result = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")
    assert result["sku_id"] == "PROD-001"
    assert result["quantity"] == 10
    assert result["status"] == "active"
    assert result["expires_at"] > datetime.utcnow()

    stock = service.get_stock(db, "PROD-001")
    assert stock["available"] == 100
    assert stock["reserved"] == 10


def test_create_reservation_insufficient_stock(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 5)

    with pytest.raises(InsufficientStockError):
        service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")


def test_create_reservation_idempotent(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    result1 = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")
    result2 = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")

    assert result1["reservation_id"] == result2["reservation_id"]

    stock = service.get_stock(db, "PROD-001")
    assert stock["reserved"] == 10


def test_confirm_reservation_happy_path(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    reservation = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")
    order = service.confirm_reservation(db, reservation["reservation_id"], "idempotency-key-1")

    assert order["sku_id"] == "PROD-001"
    assert order["quantity"] == 10
    assert order["status"] == "confirmed"


def test_confirm_nonexistent_reservation(service, db):
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(db, "nonexistent", "idempotency-key-1")


def test_confirm_expired_reservation(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    reservation = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")

    expired_record = service.repo.get_reservation(db, reservation["reservation_id"])
    expired_record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(db, reservation["reservation_id"], "idempotency-key-1")


def test_cancel_reservation_happy_path(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    reservation = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")
    result = service.cancel_reservation(db, reservation["reservation_id"])

    assert result["status"] == "cancelled"

    stock = service.get_stock(db, "PROD-001")
    assert stock["reserved"] == 0


def test_cancel_nonexistent_reservation(service, db):
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(db, "nonexistent")


def test_cancel_already_confirmed_reservation(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    reservation = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")
    service.confirm_reservation(db, reservation["reservation_id"], "idempotency-key-1")

    result = service.cancel_reservation(db, reservation["reservation_id"])
    assert result["status"] == "confirmed"


def test_get_order(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 100)

    reservation = service.create_reservation(db, "PROD-001", 10, "idempotency-key-1")
    order = service.confirm_reservation(db, reservation["reservation_id"], "idempotency-key-1")

    result = service.get_order(db, order["order_id"])
    assert result["order_id"] == order["order_id"]
    assert result["quantity"] == 10


def test_get_nonexistent_order(service, db):
    with pytest.raises(ValueError):
        service.get_order(db, "nonexistent")


def test_list_orders_empty(service, db):
    result = service.list_orders(db)
    assert result["orders"] == []
    assert result["next_cursor"] is None


def test_list_orders_with_pagination(service, db):
    service.create_sku(db, "PROD-001", "Widget")
    service.adjust_stock(db, "PROD-001", 1000)

    for i in range(15):
        reservation = service.create_reservation(db, "PROD-001", 1, f"idempotency-key-{i}")
        service.confirm_reservation(db, reservation["reservation_id"], f"idempotency-key-{i}")

    result = service.list_orders(db, limit=10)
    assert len(result["orders"]) == 10
    assert result["next_cursor"] is not None

    result_page2 = service.list_orders(db, limit=10, cursor=result["next_cursor"])
    assert len(result_page2["orders"]) == 5
    assert result_page2["next_cursor"] is None
