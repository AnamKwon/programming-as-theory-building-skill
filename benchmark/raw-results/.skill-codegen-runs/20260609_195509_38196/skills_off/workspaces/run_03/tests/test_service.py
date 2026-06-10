from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationState
from commerce_service.service import Commerce, ServiceError


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def commerce(db_session):
    return Commerce(db_session, reservation_ttl_minutes=1)


class TestSKU:
    def test_create_sku(self, commerce):
        result = commerce.create_sku("laptop", initial_stock=10)
        assert result["name"] == "laptop"
        assert result["stock"] == 10
        assert result["id"] is not None

    def test_create_duplicate_sku_fails(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        with pytest.raises(ServiceError) as exc_info:
            commerce.create_sku("laptop", initial_stock=5)
        assert exc_info.value.code == "SKU_EXISTS"

    def test_adjust_stock_positive(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        result = commerce.adjust_stock(1, 5)
        assert result["stock"] == 15

    def test_adjust_stock_negative(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        result = commerce.adjust_stock(1, -5)
        assert result["stock"] == 5

    def test_adjust_stock_below_zero_fails(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        with pytest.raises(ServiceError) as exc_info:
            commerce.adjust_stock(1, -15)
        assert exc_info.value.code == "INSUFFICIENT_STOCK"

    def test_adjust_stock_nonexistent_sku_fails(self, commerce):
        with pytest.raises(ServiceError) as exc_info:
            commerce.adjust_stock(999, 5)
        assert exc_info.value.code == "SKU_NOT_FOUND"


class TestReservation:
    def test_create_reservation_success(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        result = commerce.create_reservation(1, 5, "idempotency-key-1")
        assert result["sku_id"] == 1
        assert result["quantity"] == 5
        assert result["state"] == ReservationState.PENDING.value
        assert result["expires_at"] > datetime.now(timezone.utc)

    def test_create_reservation_insufficient_stock_fails(self, commerce):
        commerce.create_sku("laptop", initial_stock=3)
        with pytest.raises(ServiceError) as exc_info:
            commerce.create_reservation(1, 5, "idempotency-key-1")
        assert exc_info.value.code == "INSUFFICIENT_STOCK"

    def test_create_reservation_idempotent(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        result1 = commerce.create_reservation(1, 5, "idempotency-key-1")
        result2 = commerce.create_reservation(1, 5, "idempotency-key-1")
        assert result1["id"] == result2["id"]

    def test_create_reservation_nonexistent_sku_fails(self, commerce):
        with pytest.raises(ServiceError) as exc_info:
            commerce.create_reservation(999, 5, "idempotency-key-1")
        assert exc_info.value.code == "SKU_NOT_FOUND"

    def test_confirm_reservation_success(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        result = commerce.confirm_reservation(1)
        assert result["state"] == ReservationState.CONFIRMED.value

    def test_confirm_reservation_already_confirmed(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        commerce.confirm_reservation(1)
        result = commerce.confirm_reservation(1)
        assert result["state"] == ReservationState.CONFIRMED.value

    def test_confirm_reservation_nonexistent_fails(self, commerce):
        with pytest.raises(ServiceError) as exc_info:
            commerce.confirm_reservation(999)
        assert exc_info.value.code == "RESERVATION_NOT_FOUND"

    def test_confirm_expired_reservation_fails(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")

        import time
        time.sleep(1.1)

        with pytest.raises(ServiceError) as exc_info:
            commerce.confirm_reservation(1)
        assert exc_info.value.code == "RESERVATION_EXPIRED"

    def test_cancel_reservation_success(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        result = commerce.cancel_reservation(1)
        assert result["state"] == ReservationState.CANCELLED.value

    def test_cancel_reservation_restores_stock(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        commerce.cancel_reservation(1)

        sku = commerce.repo.get_sku(1)
        assert sku.stock == 10

    def test_cancel_confirmed_reservation_fails(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        commerce.confirm_reservation(1)
        with pytest.raises(ServiceError) as exc_info:
            commerce.cancel_reservation(1)
        assert exc_info.value.code == "INVALID_STATE"

    def test_idempotency_key_reuse_after_cancel_fails(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        commerce.cancel_reservation(1)
        with pytest.raises(ServiceError) as exc_info:
            commerce.create_reservation(1, 5, "idempotency-key-1")
        assert exc_info.value.code == "KEY_ALREADY_USED"


class TestOrder:
    def test_order_created_on_confirm(self, commerce):
        commerce.create_sku("laptop", initial_stock=10)
        commerce.create_reservation(1, 5, "idempotency-key-1")
        commerce.confirm_reservation(1)

        orders, _ = commerce.repo.get_orders_paginated()
        assert len(orders) == 1
        assert orders[0].sku_id == 1
        assert orders[0].quantity == 5

    def test_get_orders_pagination(self, commerce):
        commerce.create_sku("laptop", initial_stock=100)
        for i in range(15):
            commerce.create_reservation(1, 1, f"key-{i}")
            commerce.confirm_reservation(i + 1)

        result = commerce.get_orders(limit=10)
        assert len(result["items"]) == 10
        assert result["next_cursor"] is not None

        result2 = commerce.get_orders(limit=10, cursor=result["next_cursor"])
        assert len(result2["items"]) == 5
        assert result2["next_cursor"] is None
