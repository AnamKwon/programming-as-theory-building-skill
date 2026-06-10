import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.service import CommerceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


class TestSKUManagement:
    def test_create_sku(self, service):
        result = service.create_sku("SKU-001", 100)
        assert result["sku"] == "SKU-001"
        assert result["stock"] == 100

    def test_create_duplicate_sku_raises_error(self, service):
        service.create_sku("SKU-001", 100)
        with pytest.raises(Exception):
            service.create_sku("SKU-001", 50)

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", 50)
        assert result["stock"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU-001", 100)
        result = service.adjust_stock("SKU-001", -30)
        assert result["stock"] == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(Exception):
            service.adjust_stock("NONEXISTENT", 50)

    def test_adjust_stock_below_zero_fails(self, service):
        service.create_sku("SKU-001", 50)
        with pytest.raises(Exception):
            service.adjust_stock("SKU-001", -100)


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 30, "idempotency-1")
        assert result.id > 0
        assert result.sku == "SKU-001"
        assert result.quantity == 30
        assert result.status == "PENDING"

    def test_create_reservation_deducts_stock(self, service):
        service.create_sku("SKU-001", 100)
        service.create_reservation("SKU-001", 30, "idempotency-1")

        sku = service.repo.get_sku_by_code("SKU-001")
        assert sku.stock_level == 70

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU-001", 20)
        with pytest.raises(Exception) as exc_info:
            service.create_reservation("SKU-001", 30, "idempotency-1")
        assert "Insufficient stock" in str(exc_info.value)

    def test_idempotent_reservation_retry(self, service):
        service.create_sku("SKU-001", 100)
        result1 = service.create_reservation("SKU-001", 30, "idempotency-1")

        sku_after_first = service.repo.get_sku_by_code("SKU-001")
        stock_after_first = sku_after_first.stock_level

        result2 = service.create_reservation("SKU-001", 30, "idempotency-1")

        assert result1.id == result2.id
        assert result1.quantity == result2.quantity

        sku_after_second = service.repo.get_sku_by_code("SKU-001")
        assert sku_after_second.stock_level == stock_after_first

    def test_confirm_reservation_success(self, service):
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
        result = service.confirm_reservation(reservation.id)
        assert result.status == "CONFIRMED"

    def test_confirm_creates_order(self, service):
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.confirm_reservation(reservation.id)

        orders, total = service.repo.get_orders()
        assert len(orders) == 1
        assert orders[0].reservation_id == reservation.id

    def test_confirm_non_pending_reservation_fails(self, service):
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.confirm_reservation(reservation.id)

        with pytest.raises(Exception) as exc_info:
            service.confirm_reservation(reservation.id)
        assert "non-PENDING" in str(exc_info.value)

    def test_reservation_expiration(self, service):
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 30, "idempotency-1")

        reservation = service.repo.get_reservation_by_id(result.id)
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        service.repo.db.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (expired_time, result.id),
        )
        service.repo.db.commit()

        with pytest.raises(Exception) as exc_info:
            service.confirm_reservation(result.id)
        assert "expired" in str(exc_info.value)

    def test_expiration_restores_stock(self, service):
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 30, "idempotency-1")

        sku_after_reserve = service.repo.get_sku_by_code("SKU-001")
        assert sku_after_reserve.stock_level == 70

        reservation = service.repo.get_reservation_by_id(result.id)
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        service.repo.db.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (expired_time, result.id),
        )
        service.repo.db.commit()

        try:
            service.confirm_reservation(result.id)
        except Exception:
            pass

        sku_after_expiry = service.repo.get_sku_by_code("SKU-001")
        assert sku_after_expiry.stock_level == 100

    def test_cancel_reservation_success(self, service):
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 30, "idempotency-1")
        cancelled = service.cancel_reservation(result.id)
        assert cancelled.status == "CANCELLED"

    def test_cancel_restores_stock(self, service):
        service.create_sku("SKU-001", 100)
        result = service.create_reservation("SKU-001", 30, "idempotency-1")

        sku_after_reserve = service.repo.get_sku_by_code("SKU-001")
        assert sku_after_reserve.stock_level == 70

        service.cancel_reservation(result.id)

        sku_after_cancel = service.repo.get_sku_by_code("SKU-001")
        assert sku_after_cancel.stock_level == 100

    def test_cancel_non_pending_fails(self, service):
        service.create_sku("SKU-001", 100)
        reservation = service.create_reservation("SKU-001", 30, "idempotency-1")
        service.confirm_reservation(reservation.id)

        with pytest.raises(Exception) as exc_info:
            service.cancel_reservation(reservation.id)
        assert "non-PENDING" in str(exc_info.value)


class TestOrders:
    def test_get_orders_pagination_default(self, service):
        service.create_sku("SKU-001", 100)
        for i in range(5):
            res = service.create_reservation("SKU-001", 10, f"id-{i}")
            service.confirm_reservation(res.id)

        result = service.get_orders(page=1, size=10)
        assert result["total"] == 5
        assert len(result["orders"]) == 5

    def test_get_orders_pagination_offset(self, service):
        service.create_sku("SKU-001", 200)
        for i in range(15):
            res = service.create_reservation("SKU-001", 10, f"id-{i}")
            service.confirm_reservation(res.id)

        result_page1 = service.get_orders(page=1, size=10)
        result_page2 = service.get_orders(page=2, size=10)

        assert len(result_page1["orders"]) == 10
        assert len(result_page2["orders"]) == 5
        assert result_page1["orders"][0].id != result_page2["orders"][0].id
