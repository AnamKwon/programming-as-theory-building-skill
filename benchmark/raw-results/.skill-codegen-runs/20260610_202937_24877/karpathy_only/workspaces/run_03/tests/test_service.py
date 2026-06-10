import pytest
import time
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def repo():
    r = Repository(":memory:")
    yield r
    r.clear_all()


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKUOperations:
    def test_create_sku(self, service):
        result = service.create_sku("SKU-001", 100)
        assert result["sku"] == "SKU-001"
        assert result["available_stock"] == 100
        assert result["id"] is not None

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU-001", 50)
        result = service.adjust_stock("SKU-001", 25)
        assert result["available_stock"] == 75

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU-001", 50)
        result = service.adjust_stock("SKU-001", -20)
        assert result["available_stock"] == 30

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 30, "idempotency-1")
        assert result["status"] == "PENDING"
        assert result["quantity"] == 30
        assert result["idempotency_key"] == "idempotency-1"

    def test_create_reservation_deducts_stock(self, service):
        service.create_sku("SKU-001", 100)
        service.create_reservation("SKU-001", 30, "idempotency-1")
        sku = service.repo.get_sku_by_name("SKU-001")
        assert sku["available_stock"] == 70

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-001", 20)
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation("SKU-001", 30, "idempotency-1")

    def test_reservation_idempotency(self, service):
        service.create_sku("SKU-001", 100)
        result1 = service.create_reservation("SKU-001", 30, "idempotency-1")
        result2 = service.create_reservation("SKU-001", 30, "idempotency-1")

        assert result1["id"] == result2["id"]
        sku = service.repo.get_sku_by_name("SKU-001")
        assert sku["available_stock"] == 70

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="SKU not found"):
            service.create_reservation("NONEXISTENT", 10, "idempotency-1")


class TestConfirmation:
    def test_confirm_reservation(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")
        result = service.confirm_reservation(res["id"])

        assert result["status"] == "CONFIRMED"

    def test_confirm_creates_order(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.confirm_reservation(res["id"])

        orders, _ = service.repo.get_orders(1, 10)
        assert len(orders) == 1
        assert orders[0]["sku"] == "SKU-001"
        assert orders[0]["quantity"] == 30

    def test_confirm_nonpending_reservation(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.confirm_reservation(res["id"])

        with pytest.raises(ValueError, match="not PENDING"):
            service.confirm_reservation(res["id"])

    def test_confirm_expired_reservation(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")

        time.sleep(0.35)

        with pytest.raises(ValueError, match="Reservation expired"):
            service.confirm_reservation(res["id"])

        updated = service.repo.get_reservation_by_id(res["id"])
        assert updated["status"] == "EXPIRED"

        sku = service.repo.get_sku_by_name("SKU-001")
        assert sku["available_stock"] == 100


class TestCancellation:
    def test_cancel_reservation(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")
        result = service.cancel_reservation(res["id"])

        assert result["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.cancel_reservation(res["id"])

        sku = service.repo.get_sku_by_name("SKU-001")
        assert sku["available_stock"] == 100

    def test_cancel_nonpending_reservation(self, service):
        service.create_sku("SKU-001", 100)
        res = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.confirm_reservation(res["id"])

        with pytest.raises(ValueError, match="not PENDING"):
            service.cancel_reservation(res["id"])


class TestOrders:
    def test_get_orders_pagination(self, service):
        service.create_sku("SKU-001", 1000)

        for i in range(15):
            res = service.create_reservation("SKU-001", 10, f"idempotency-{i}")
            service.confirm_reservation(res["id"])

        result = service.get_orders(1, 10)
        assert len(result["orders"]) == 10
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 15

    def test_get_orders_second_page(self, service):
        service.create_sku("SKU-001", 1000)

        for i in range(15):
            res = service.create_reservation("SKU-001", 10, f"idempotency-{i}")
            service.confirm_reservation(res["id"])

        result = service.get_orders(2, 10)
        assert len(result["orders"]) == 5
        assert result["page"] == 2
