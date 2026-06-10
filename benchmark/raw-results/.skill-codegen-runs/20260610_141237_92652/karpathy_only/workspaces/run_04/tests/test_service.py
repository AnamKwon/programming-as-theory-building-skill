import time
import pytest
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repo):
    return CommerceService(repo)


class TestSKUManagement:
    def test_create_sku(self, service):
        sku_id = service.create_sku("PROD001", 100)
        assert sku_id > 0
        assert service.repo.get_sku_stock("PROD001") == 100

    def test_adjust_stock_increase(self, service):
        service.create_sku("PROD001", 100)
        updated_stock = service.adjust_stock("PROD001", 50)
        assert updated_stock == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("PROD001", 100)
        updated_stock = service.adjust_stock("PROD001", -30)
        assert updated_stock == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        result = service.adjust_stock("NONEXISTENT", 10)
        assert result is None


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("PROD001", 100)
        result, status_code = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        assert status_code == 201
        assert result["id"] > 0
        assert result["quantity"] == 30
        assert result["status"] == "PENDING"
        assert service.repo.get_sku_stock("PROD001") == 70

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("PROD001", 50)
        result, status_code = service.create_reservation(
            "PROD001", 100, "idempotency-key-1"
        )
        assert status_code == 400
        assert "Insufficient stock" in result["detail"]
        assert service.repo.get_sku_stock("PROD001") == 50

    def test_create_reservation_idempotency(self, service):
        service.create_sku("PROD001", 100)
        result1, status1 = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        result2, status2 = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        assert status1 == 201
        assert status2 == 201
        assert result1["id"] == result2["id"]
        assert service.repo.get_sku_stock("PROD001") == 70

    def test_create_reservation_nonexistent_sku(self, service):
        result, status_code = service.create_reservation(
            "NONEXISTENT", 30, "idempotency-key-1"
        )
        assert status_code == 400
        assert "SKU not found" in result["detail"]


class TestConfirmReservation:
    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("PROD001", 100)
        res_result, _ = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        reservation_id = res_result["id"]

        conf_result, status_code = service.confirm_reservation(reservation_id)
        assert status_code == 200
        assert conf_result["status"] == "CONFIRMED"
        assert conf_result["order_id"] > 0

    def test_confirm_reservation_nonexistent(self, service):
        result, status_code = service.confirm_reservation(999)
        assert status_code == 400
        assert "Reservation not found" in result["detail"]

    def test_confirm_reservation_not_pending(self, service):
        service.create_sku("PROD001", 100)
        res_result, _ = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        reservation_id = res_result["id"]

        service.confirm_reservation(reservation_id)
        result, status_code = service.confirm_reservation(reservation_id)
        assert status_code == 400
        assert "must be PENDING" in result["detail"]

    def test_confirm_reservation_expired(self, service, monkeypatch):
        import time as time_module

        service.create_sku("PROD001", 100)

        # Set a fixed creation time
        creation_time = 1000.0
        monkeypatch.setattr("src.commerce_service.service.time.time", lambda: creation_time)

        res_result, _ = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        reservation_id = res_result["id"]

        # Now set time to after expiry
        expiry_time = creation_time + 400
        monkeypatch.setattr("src.commerce_service.service.time.time", lambda: expiry_time)

        result, status_code = service.confirm_reservation(reservation_id)
        assert status_code == 400
        assert "Reservation expired" in result["detail"]
        reservation = service.repo.get_reservation(reservation_id)
        assert reservation["status"] == "EXPIRED"
        assert service.repo.get_sku_stock("PROD001") == 100


class TestCancelReservation:
    def test_cancel_reservation_happy_path(self, service):
        service.create_sku("PROD001", 100)
        res_result, _ = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        reservation_id = res_result["id"]

        result, status_code = service.cancel_reservation(reservation_id)
        assert status_code == 200
        assert result["status"] == "CANCELLED"
        assert result["stock_restored"] == 30
        assert service.repo.get_sku_stock("PROD001") == 100

    def test_cancel_reservation_nonexistent(self, service):
        result, status_code = service.cancel_reservation(999)
        assert status_code == 400
        assert "Reservation not found" in result["detail"]

    def test_cancel_reservation_not_pending(self, service):
        service.create_sku("PROD001", 100)
        res_result, _ = service.create_reservation(
            "PROD001", 30, "idempotency-key-1"
        )
        reservation_id = res_result["id"]

        service.confirm_reservation(reservation_id)
        result, status_code = service.cancel_reservation(reservation_id)
        assert status_code == 400
        assert "must be PENDING" in result["detail"]


class TestOrderRetrieval:
    def test_get_orders_empty(self, service):
        result = service.get_orders()
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 0
        assert len(result["orders"]) == 0

    def test_get_orders_pagination(self, service):
        service.create_sku("PROD001", 1000)
        for i in range(25):
            res_result, _ = service.create_reservation(
                "PROD001", 10, f"idempotency-key-{i}"
            )
            service.confirm_reservation(res_result["id"])

        result_page_1 = service.get_orders(page=1, size=10)
        assert result_page_1["total"] == 25
        assert len(result_page_1["orders"]) == 10
        assert result_page_1["page"] == 1

        result_page_2 = service.get_orders(page=2, size=10)
        assert len(result_page_2["orders"]) == 10
        assert result_page_2["page"] == 2

        result_page_3 = service.get_orders(page=3, size=10)
        assert len(result_page_3["orders"]) == 5
        assert result_page_3["page"] == 3
