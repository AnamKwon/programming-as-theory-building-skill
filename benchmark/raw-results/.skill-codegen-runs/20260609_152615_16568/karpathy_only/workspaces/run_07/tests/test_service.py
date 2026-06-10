import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    return CommerceService(db_session)


class TestSKUCreation:
    def test_create_sku(self, service):
        result = service.create_sku("SKU001", "Widget", 100)
        assert result["sku_id"] == "SKU001"
        assert result["name"] == "Widget"
        assert result["available_stock"] == 100
        assert result["reserved_stock"] == 0

    def test_adjust_stock_positive(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result = service.adjust_stock("SKU001", 50)
        assert result["available_stock"] == 150

    def test_adjust_stock_negative(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result = service.adjust_stock("SKU001", -30)
        assert result["available_stock"] == 70

    def test_adjust_nonexistent_sku(self, service):
        with pytest.raises(SKUNotFoundError):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    def test_create_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result = service.create_reservation("SKU001", 10)

        assert result["sku_id"] == "SKU001"
        assert result["quantity"] == 10
        assert result["status"] == "pending"
        assert result["reservation_id"]
        assert result["expires_at"] > result["created_at"]

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku("SKU001", "Widget", 50)
        with pytest.raises(InsufficientStockError):
            service.create_reservation("SKU001", 100)

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(SKUNotFoundError):
            service.create_reservation("NONEXISTENT", 10)

    def test_idempotent_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        result1 = service.create_reservation("SKU001", 10, idempotency_key="key123")
        result2 = service.create_reservation("SKU001", 10, idempotency_key="key123")

        assert result1["reservation_id"] == result2["reservation_id"]
        assert result1["status"] == result2["status"]

    def test_reservation_decreases_available_stock(self, service):
        service.create_sku("SKU001", "Widget", 100)
        service.create_reservation("SKU001", 30)

        sku_repo = service.sku_repo
        sku = sku_repo.get("SKU001")
        assert sku.available_stock == 70
        assert sku.reserved_stock == 30

    def test_confirm_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 10)
        order = service.confirm_reservation(res["reservation_id"])

        assert order["order_id"]
        assert order["status"] == "pending"
        assert len(order["items"]) == 1
        assert order["items"][0]["sku_id"] == "SKU001"
        assert order["items"][0]["quantity"] == 10

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.confirm_reservation("NONEXISTENT")

    def test_confirm_already_confirmed_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 10)
        service.confirm_reservation(res["reservation_id"])

        with pytest.raises(InvalidStateTransitionError):
            service.confirm_reservation(res["reservation_id"])

    def test_cancel_reservation_happy_path(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 30)

        result = service.cancel_reservation(res["reservation_id"])
        assert result["status"] == "cancelled"

        sku_repo = service.sku_repo
        sku = sku_repo.get("SKU001")
        assert sku.available_stock == 100
        assert sku.reserved_stock == 0

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ReservationNotFoundError):
            service.cancel_reservation("NONEXISTENT")

    def test_cancel_already_confirmed_reservation(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 10)
        service.confirm_reservation(res["reservation_id"])

        with pytest.raises(InvalidStateTransitionError):
            service.cancel_reservation(res["reservation_id"])


class TestOrderLookup:
    def test_get_order(self, service):
        service.create_sku("SKU001", "Widget", 100)
        res = service.create_reservation("SKU001", 10)
        order_result = service.confirm_reservation(res["reservation_id"])

        order = service.get_order(order_result["order_id"])
        assert order["order_id"] == order_result["order_id"]
        assert order["status"] == "pending"
        assert len(order["items"]) == 1

    def test_list_orders_pagination(self, service):
        service.create_sku("SKU001", "Widget", 1000)

        for i in range(25):
            res = service.create_reservation("SKU001", 10)
            service.confirm_reservation(res["reservation_id"])

        page1 = service.list_orders(page=1, page_size=10)
        assert len(page1["items"]) == 10
        assert page1["total"] == 25
        assert page1["page"] == 1
        assert page1["pages"] == 3

        page3 = service.list_orders(page=3, page_size=10)
        assert len(page3["items"]) == 5
        assert page3["page"] == 3
