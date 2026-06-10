import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from commerce_service.repository import Repository, init_db
from commerce_service.service import Service


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_commerce.db"
    original_db_path = Path(__file__).parent.parent / "commerce.db"

    import commerce_service.repository as repo_module
    original_path = repo_module.DB_PATH
    repo_module.DB_PATH = db_path

    init_db()
    yield db_path

    repo_module.DB_PATH = original_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def repo(temp_db):
    r = Repository()
    yield r
    r.close()


@pytest.fixture
def service(repo):
    return Service(repo)


class TestSKUOperations:
    def test_create_sku(self, service, repo):
        result = service.create_sku("SKU001", 100)
        assert result is not None
        assert result["sku"] == "SKU001"
        assert result["available_stock"] == 100

    def test_create_duplicate_sku_fails(self, service):
        service.create_sku("SKU001", 100)
        result = service.create_sku("SKU001", 50)
        assert result is None

    def test_adjust_stock_increase(self, service):
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["available_stock"] == 150

    def test_adjust_stock_decrease(self, service):
        service.create_sku("SKU001", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["available_stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        result = service.adjust_stock("UNKNOWN", 10)
        assert result is None


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU001", 100)
        result, status = service.create_reservation("SKU001", 30, "key-1")
        assert status == "created"
        assert result is not None
        assert result["sku"] == "SKU001"
        assert result["quantity"] == 30
        assert result["status"] == "PENDING"
        assert result["idempotency_key"] == "key-1"

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", 100)
        result, status = service.create_reservation("SKU001", 150, "key-1")
        assert status == "insufficient_stock"
        assert result is None

    def test_create_reservation_sku_not_found(self, service):
        result, status = service.create_reservation("UNKNOWN", 10, "key-1")
        assert status == "sku_not_found"
        assert result is None

    def test_idempotent_reservation(self, service):
        service.create_sku("SKU001", 100)
        result1, status1 = service.create_reservation("SKU001", 30, "key-1")
        result2, status2 = service.create_reservation("SKU001", 30, "key-1")

        assert status2 == "idempotent"
        assert result1["id"] == result2["id"]
        assert result1["sku"] == result2["sku"]
        assert result1["quantity"] == result2["quantity"]

    def test_stock_deducted_on_reservation(self, service, repo):
        service.create_sku("SKU001", 100)
        service.create_reservation("SKU001", 30, "key-1")
        sku = repo.get_sku("SKU001")
        assert sku["available_stock"] == 70


class TestReservationConfirmation:
    def test_confirm_reservation_success(self, service, repo):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation("SKU001", 30, "key-1")
        result, status = service.confirm_reservation(reservation["id"])

        assert status == "confirmed"
        assert isinstance(result, tuple)
        confirmed_reservation, order = result
        assert confirmed_reservation["status"] == "CONFIRMED"
        assert order is not None
        assert order["reservation_id"] == reservation["id"]

    def test_confirm_nonexistent_reservation(self, service):
        result, status = service.confirm_reservation(999)
        assert status == "not_found"
        assert result is None

    def test_confirm_non_pending_reservation(self, service):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation("SKU001", 30, "key-1")
        service.confirm_reservation(reservation["id"])
        result, status = service.confirm_reservation(reservation["id"])
        assert status == "invalid_state"
        assert result is None

    def test_confirm_expired_reservation(self, service, repo, temp_db):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation("SKU001", 30, "key-1")

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=400)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation["id"]),
        )
        conn.commit()
        conn.close()

        result, status = service.confirm_reservation(reservation["id"])
        assert status == "expired"
        assert result is None

        updated_reservation = repo.get_reservation(reservation["id"])
        assert updated_reservation["status"] == "EXPIRED"

        sku = repo.get_sku("SKU001")
        assert sku["available_stock"] == 100


class TestReservationCancellation:
    def test_cancel_reservation_success(self, service, repo):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation("SKU001", 30, "key-1")
        result, status = service.cancel_reservation(reservation["id"])

        assert status == "cancelled"
        assert result["status"] == "CANCELLED"

        sku = repo.get_sku("SKU001")
        assert sku["available_stock"] == 100

    def test_cancel_nonexistent_reservation(self, service):
        result, status = service.cancel_reservation(999)
        assert status == "not_found"
        assert result is None

    def test_cancel_non_pending_reservation(self, service):
        service.create_sku("SKU001", 100)
        reservation, _ = service.create_reservation("SKU001", 30, "key-1")
        service.confirm_reservation(reservation["id"])
        result, status = service.cancel_reservation(reservation["id"])
        assert status == "invalid_state"
        assert result is None
