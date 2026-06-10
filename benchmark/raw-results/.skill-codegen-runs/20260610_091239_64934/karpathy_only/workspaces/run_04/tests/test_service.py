import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import HTTPException

from src.commerce_service.repository import Repository
from src.commerce_service.service import Service
from src.commerce_service.models import CreateSKURequest, CreateReservationRequest


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def repo(temp_db):
    r = Repository(temp_db)
    r.init_db()
    return r


@pytest.fixture
def service(repo):
    return Service(repo)


class TestCreateSKU:
    def test_create_sku_success(self, service):
        req = CreateSKURequest(sku_code="PROD001", name="Test Product", initial_stock=100)
        sku = service.create_sku(req)
        assert sku["sku_code"] == "PROD001"
        assert sku["name"] == "Test Product"
        assert sku["stock"] == 100

    def test_create_sku_duplicate(self, service):
        req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=50)
        service.create_sku(req)
        with pytest.raises(HTTPException) as exc_info:
            service.create_sku(req)
        assert exc_info.value.status_code == 409


class TestAdjustStock:
    def test_adjust_stock_increase(self, service):
        req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(req)
        sku_id = sku["id"]

        updated = service.adjust_stock(sku_id, 50)
        assert updated["stock"] == 150

    def test_adjust_stock_decrease(self, service):
        req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(req)
        sku_id = sku["id"]

        updated = service.adjust_stock(sku_id, -30)
        assert updated["stock"] == 70

    def test_adjust_stock_negative_result(self, service):
        req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=50)
        sku = service.create_sku(req)
        sku_id = sku["id"]

        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock(sku_id, -100)
        assert exc_info.value.status_code == 400

    def test_adjust_stock_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.adjust_stock(999, 10)
        assert exc_info.value.status_code == 404


class TestOrderAndReservation:
    def test_create_order(self, service):
        order = service.create_order()
        assert order["status"] == "pending"
        assert "created_at" in order
        assert order["reservations"] == []

    def test_get_order(self, service):
        order = service.create_order()
        retrieved = service.get_order(order["id"])
        assert retrieved["id"] == order["id"]

    def test_get_order_not_found(self, service):
        with pytest.raises(HTTPException) as exc_info:
            service.get_order(999)
        assert exc_info.value.status_code == 404

    def test_create_reservation_happy_path(self, service):
        sku_req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(sku_req)

        order = service.create_order()

        res_req = CreateReservationRequest(
            sku_id=sku["id"],
            quantity=30,
            idempotency_key="key-001",
        )
        reservation = service.create_reservation(order["id"], res_req)
        assert reservation["sku_id"] == sku["id"]
        assert reservation["quantity"] == 30
        assert reservation["status"] == "reserved"

        updated_sku = service.repo.get_sku(sku["id"])
        assert updated_sku["stock"] == 70

    def test_create_reservation_insufficient_stock(self, service):
        sku_req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=50)
        sku = service.create_sku(sku_req)

        order = service.create_order()

        res_req = CreateReservationRequest(
            sku_id=sku["id"],
            quantity=100,
            idempotency_key="key-001",
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation(order["id"], res_req)
        assert exc_info.value.status_code == 400
        assert "Insufficient stock" in exc_info.value.detail

    def test_create_reservation_idempotent(self, service):
        sku_req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(sku_req)

        order = service.create_order()

        res_req = CreateReservationRequest(
            sku_id=sku["id"],
            quantity=30,
            idempotency_key="key-001",
        )
        res1 = service.create_reservation(order["id"], res_req)
        res2 = service.create_reservation(order["id"], res_req)

        assert res1["id"] == res2["id"]

        updated_sku = service.repo.get_sku(sku["id"])
        assert updated_sku["stock"] == 70

    def test_create_reservation_sku_not_found(self, service):
        order = service.create_order()
        res_req = CreateReservationRequest(
            sku_id=999,
            quantity=10,
            idempotency_key="key-001",
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_reservation(order["id"], res_req)
        assert exc_info.value.status_code == 404

    def test_confirm_reservation_happy_path(self, service):
        sku_req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(sku_req)

        order = service.create_order()

        res_req = CreateReservationRequest(
            sku_id=sku["id"],
            quantity=30,
            idempotency_key="key-001",
        )
        reservation = service.create_reservation(order["id"], res_req)

        confirmed = service.confirm_reservation(order["id"], reservation["id"])
        assert confirmed["status"] == "confirmed"

    def test_confirm_reservation_expired(self, service, repo):
        sku_req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(sku_req)

        order = service.create_order()

        res_req = CreateReservationRequest(
            sku_id=sku["id"],
            quantity=30,
            idempotency_key="key-001",
        )
        reservation = service.create_reservation(order["id"], res_req)

        expired_time = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        with repo._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET expires_at = ? WHERE id = ?",
                (expired_time, reservation["id"]),
            )

        with pytest.raises(HTTPException) as exc_info:
            service.confirm_reservation(order["id"], reservation["id"])
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail

    def test_cancel_reservation_happy_path(self, service):
        sku_req = CreateSKURequest(sku_code="PROD001", name="Test", initial_stock=100)
        sku = service.create_sku(sku_req)

        order = service.create_order()

        res_req = CreateReservationRequest(
            sku_id=sku["id"],
            quantity=30,
            idempotency_key="key-001",
        )
        reservation = service.create_reservation(order["id"], res_req)

        cancelled = service.cancel_reservation(order["id"], reservation["id"])
        assert cancelled["status"] == "cancelled"

        updated_sku = service.repo.get_sku(sku["id"])
        assert updated_sku["stock"] == 100

    def test_cancel_reservation_not_found(self, service):
        order = service.create_order()
        with pytest.raises(HTTPException) as exc_info:
            service.cancel_reservation(order["id"], 999)
        assert exc_info.value.status_code == 404
