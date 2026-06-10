import pytest
from fastapi import HTTPException

from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SKU-001", "Test Product", 100)
        assert result["sku"] == "SKU-001"
        assert result["name"] == "Test Product"
        assert result["stock"] == 100

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("SKU-001", "Test Product", 100)
        with pytest.raises(HTTPException) as exc_info:
            service.create_sku("SKU-001", "Another", 50)
        assert exc_info.value.status_code == 409

    def test_adjust_stock(self, service):
        service.create_sku("SKU-001", "Product", 100)
        result = service.adjust_stock("SKU-001", 50)
        assert result["stock"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU-001", "Product", 100)
        result = service.adjust_stock("SKU-001", -30)
        assert result["stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("NONEXISTENT", 10)
        assert exc_info.value.status_code == 404

    def test_adjust_stock_negative_would_fail(self, service):
        service.create_sku("SKU-001", "Product", 50)
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock("SKU-001", -100)
        assert exc_info.value.status_code == 400


class TestReservation:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU-001", "Product", 100)
        result = service.create_reservation("SKU-001", 30, "key-1", 300)
        assert result["sku"] == "SKU-001"
        assert result["quantity"] == 30
        assert result["state"] == "pending"

        # Stock should be reduced
        sku = service.repo.get_sku("SKU-001")
        assert sku["stock"] == 70

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-001", "Product", 50)
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("SKU-001", 100, "key-1", 300)
        assert exc_info.value.status_code == 409

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation("NONEXISTENT", 10, "key-1", 300)
        assert exc_info.value.status_code == 404

    def test_idempotent_reservation_retry(self, service):
        service.create_sku("SKU-001", "Product", 100)
        res1 = service.create_reservation("SKU-001", 30, "key-1", 300)
        res2 = service.create_reservation("SKU-001", 30, "key-1", 300)
        assert res1["id"] == res2["id"]

        # Stock should only be reduced once
        sku = service.repo.get_sku("SKU-001")
        assert sku["stock"] == 70

    def test_cancel_reservation(self, service):
        service.create_sku("SKU-001", "Product", 100)
        res = service.create_reservation("SKU-001", 30, "key-1", 300)
        service.cancel_reservation(res["id"])

        # Stock should be restored
        sku = service.repo.get_sku("SKU-001")
        assert sku["stock"] == 100

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation("nonexistent")
        assert exc_info.value.status_code == 404

    def test_cancel_already_confirmed_reservation(self, service):
        service.create_sku("SKU-001", "Product", 100)
        res = service.create_reservation("SKU-001", 30, "key-1", 300)
        service.confirm_reservation(res["id"], "confirm-key-1")

        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(res["id"])
        assert exc_info.value.status_code == 409


class TestConfirmation:
    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU-001", "Product", 100)
        res = service.create_reservation("SKU-001", 30, "key-1", 300)
        order = service.confirm_reservation(res["id"], "confirm-key-1")
        assert order["state"] == "reserved"
        assert order["sku"] == "SKU-001"

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation("nonexistent", "confirm-key-1")
        assert exc_info.value.status_code == 404

    def test_confirm_already_confirmed_reservation(self, service):
        service.create_sku("SKU-001", "Product", 100)
        res = service.create_reservation("SKU-001", 30, "key-1", 300)
        service.confirm_reservation(res["id"], "confirm-key-1")

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res["id"], "confirm-key-2")
        assert exc_info.value.status_code == 409

    def test_confirm_expired_reservation(self, service, monkeypatch):
        from datetime import datetime, timedelta

        service.create_sku("SKU-001", "Product", 100)
        res = service.create_reservation("SKU-001", 30, "key-1", 1)

        # Mock datetime to simulate expiration
        def mock_utcnow():
            return datetime.fromisoformat(res["created_at"]) + timedelta(seconds=5)

        monkeypatch.setattr("commerce_service.service.datetime", type("datetime", (), {
            "fromisoformat": datetime.fromisoformat,
            "utcnow": mock_utcnow,
        }))

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(res["id"], "confirm-key-1")
        assert exc_info.value.status_code == 409


class TestOrderLookup:
    def test_list_orders_empty(self, service):
        result = service.list_orders(offset=0, limit=10)
        assert result["items"] == []
        assert result["total"] == 0

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU-001", "Product", 1000)
        for i in range(15):
            res = service.create_reservation("SKU-001", 10, f"key-{i}", 300)
            service.confirm_reservation(res["id"], f"confirm-key-{i}")

        page1 = service.list_orders(offset=0, limit=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 15
        assert page1["offset"] == 0

        page2 = service.list_orders(offset=10, limit=10)
        assert len(page2["items"]) == 5
        assert page2["offset"] == 10

    def test_get_order(self, service):
        service.create_sku("SKU-001", "Product", 100)
        res = service.create_reservation("SKU-001", 30, "key-1", 300)
        order = service.confirm_reservation(res["id"], "confirm-key-1")

        fetched = service.get_order(order["id"])
        assert fetched["id"] == order["id"]

    def test_get_nonexistent_order(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.get_order("nonexistent")
        assert exc_info.value.status_code == 404
