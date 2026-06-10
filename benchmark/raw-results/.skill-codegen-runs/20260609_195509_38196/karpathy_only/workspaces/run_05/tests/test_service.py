import pytest
import uuid
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import CommercService


@pytest.fixture
def repo():
    db_name = f"memdb_{uuid.uuid4().hex[:8]}"
    return Repository(f"sqlite:///file:{db_name}?mode=memory&cache=shared&uri=true")


@pytest.fixture
def service(repo):
    return CommercService(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", "Product A", 100)
    assert result["sku_id"] == "SKU001"
    assert result["name"] == "Product A"
    assert "created_at" in result


def test_create_duplicate_sku(service):
    service.create_sku("SKU001", "Product A", 100)
    with pytest.raises(ValueError, match="already exists"):
        service.create_sku("SKU001", "Product B", 50)


def test_adjust_stock(service):
    service.create_sku("SKU001", "Product A", 100)
    result = service.adjust_stock("SKU001", 20)
    assert result["available"] == 120
    assert result["reserved"] == 0


def test_adjust_stock_insufficient(service):
    service.create_sku("SKU001", "Product A", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.adjust_stock("SKU001", -100)


def test_create_reservation_success(service):
    service.create_sku("SKU001", "Product A", 100)
    result = service.create_reservation("SKU001", 10, "idempotency-1", 3600)
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 10
    assert result["status"] == "pending"
    assert "id" in result


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", "Product A", 5)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 10, "idempotency-1", 3600)


def test_reservation_idempotency(service):
    service.create_sku("SKU001", "Product A", 100)
    res1 = service.create_reservation("SKU001", 10, "idempotency-1", 3600)
    res2 = service.create_reservation("SKU001", 10, "idempotency-1", 3600)
    assert res1["id"] == res2["id"]


def test_confirm_reservation(service):
    service.create_sku("SKU001", "Product A", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-1", 3600)
    order = service.confirm_reservation(res["id"])
    assert order["sku_id"] == "SKU001"
    assert order["quantity"] == 10
    assert "id" in order


def test_confirm_expired_reservation(service):
    repo = service.repo
    session = repo.get_session()
    try:
        service.create_sku("SKU001", "Product A", 100)
        res = service.create_reservation("SKU001", 10, "idempotency-1", 1)

        res_obj = repo.get_reservation(session, res["id"])
        res_obj.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
        session.close()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(res["id"])
    finally:
        session.close()


def test_cancel_reservation(service):
    service.create_sku("SKU001", "Product A", 100)
    res = service.create_reservation("SKU001", 10, "idempotency-1", 3600)
    cancelled = service.cancel_reservation(res["id"])
    assert cancelled["status"] == "cancelled"


def test_cancel_nonexistent_reservation(service):
    with pytest.raises(ValueError, match="not found"):
        service.cancel_reservation("nonexistent")


def test_list_orders(service):
    service.create_sku("SKU001", "Product A", 100)
    service.create_sku("SKU002", "Product B", 50)
    res1 = service.create_reservation("SKU001", 10, "idempotency-1", 3600)
    res2 = service.create_reservation("SKU002", 5, "idempotency-2", 3600)

    service.confirm_reservation(res1["id"])

    result = service.list_orders(0, 10)
    assert result["total"] >= 1
    assert len(result["items"]) >= 1


def test_stock_reserved_on_reservation(service):
    service.create_sku("SKU001", "Product A", 100)
    service.create_reservation("SKU001", 30, "idempotency-1", 3600)

    repo = service.repo
    session = repo.get_session()
    stock = repo.get_stock(session, "SKU001")
    assert stock.available == 70
    assert stock.reserved == 30
    session.close()


def test_stock_released_on_cancel(service):
    service.create_sku("SKU001", "Product A", 100)
    res = service.create_reservation("SKU001", 30, "idempotency-1", 3600)
    service.cancel_reservation(res["id"])

    repo = service.repo
    session = repo.get_session()
    stock = repo.get_stock(session, "SKU001")
    assert stock.available == 100
    assert stock.reserved == 0
    session.close()
