import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["initial_stock"] == 100


def test_adjust_stock(service):
    service.create_sku("SKU-001", 100)
    result = service.adjust_stock("SKU-001", -20)
    assert result["available_stock"] == 80

    result = service.adjust_stock("SKU-001", 30)
    assert result["available_stock"] == 110


def test_adjust_stock_not_found(service):
    with pytest.raises(HTTPException) as exc:
        service.adjust_stock("SKU-MISSING", 10)
    assert exc.value.status_code == 404


def test_create_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    result = service.create_reservation("SKU-001", 50, "idem-key-1")
    assert result["sku"] == "SKU-001"
    assert result["quantity"] == 50
    assert result["status"] == "PENDING"
    assert result["id"] == 1

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.available_stock == 50


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU-001", 30)
    with pytest.raises(HTTPException) as exc:
        service.create_reservation("SKU-001", 50, "idem-key-1")
    assert exc.value.status_code == 400
    assert "Insufficient stock" in exc.value.detail

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.available_stock == 30


def test_create_reservation_idempotency(service):
    service.create_sku("SKU-001", 100)
    result1 = service.create_reservation("SKU-001", 50, "idem-key-1")
    result2 = service.create_reservation("SKU-001", 60, "idem-key-1")

    assert result1["id"] == result2["id"]
    assert result1["quantity"] == result2["quantity"]
    assert result1["quantity"] == 50

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.available_stock == 50


def test_confirm_reservation_happy_path(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 50, "idem-key-1")
    order = service.confirm_reservation(res["id"])

    assert order["sku"] == "SKU-001"
    assert order["quantity"] == 50
    assert order["reservation_id"] == res["id"]

    reservation = service.repo.get_reservation_by_id(res["id"])
    assert reservation.status == "CONFIRMED"


def test_confirm_reservation_expired(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 50, "idem-key-1")

    reservation = service.repo.get_reservation_by_id(res["id"])
    old_time = datetime.utcnow() - timedelta(seconds=301)
    session = service.repo.get_session()
    try:
        reservation_db = session.query(service.repo.SessionLocal.kw["bind"].metadata.tables["reservations"]).filter_by(id=res["id"]).first()
    finally:
        session.close()

    with pytest.raises(HTTPException) as exc:
        service.confirm_reservation(res["id"])
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()

    reservation = service.repo.get_reservation_by_id(res["id"])
    assert reservation.status == "EXPIRED"

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.available_stock == 100


def test_cancel_reservation(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 50, "idem-key-1")
    result = service.cancel_reservation(res["id"])

    assert result["status"] == "CANCELLED"

    reservation = service.repo.get_reservation_by_id(res["id"])
    assert reservation.status == "CANCELLED"

    sku = service.repo.get_sku_by_name("SKU-001")
    assert sku.available_stock == 100


def test_cancel_non_pending_reservation(service):
    service.create_sku("SKU-001", 100)
    res = service.create_reservation("SKU-001", 50, "idem-key-1")
    service.confirm_reservation(res["id"])

    with pytest.raises(HTTPException) as exc:
        service.cancel_reservation(res["id"])
    assert exc.value.status_code == 400


def test_get_orders_pagination(service):
    service.create_sku("SKU-001", 100)

    for i in range(25):
        res = service.create_reservation("SKU-001", 1, f"idem-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.get_orders(page=1, size=10)
    assert len(page1["items"]) == 10
    assert page1["total"] == 25
    assert page1["page"] == 1
    assert page1["size"] == 10

    page2 = service.get_orders(page=2, size=10)
    assert len(page2["items"]) == 10

    page3 = service.get_orders(page=3, size=10)
    assert len(page3["items"]) == 5
