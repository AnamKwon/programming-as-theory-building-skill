import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from commerce_service.repository import Repository, get_session_factory
from commerce_service.service import CommerceService, ValidationError, NotFoundError
from commerce_service.models import Base, RESERVATION_TTL_MINUTES
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def service(test_db: Session) -> CommerceService:
    repo = Repository(test_db)
    return CommerceService(repo)


class TestSKUAndStock:
    def test_create_sku(self, service: CommerceService):
        sku = service.create_sku("sku-001", "Widget A")
        assert sku.id == "sku-001"
        assert sku.name == "Widget A"

    def test_create_duplicate_sku_fails(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        with pytest.raises(Exception, match="already exists"):
            service.create_sku("sku-001", "Widget B")

    def test_adjust_stock(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        inv = service.adjust_stock("sku-001", 100)
        assert inv.quantity == 100
        assert inv.reserved == 0

    def test_adjust_stock_nonexistent_sku_fails(self, service: CommerceService):
        with pytest.raises(NotFoundError):
            service.adjust_stock("sku-invalid", 100)

    def test_adjust_stock_negative_fails(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 50)
        with pytest.raises(ValidationError, match="negative"):
            service.adjust_stock("sku-001", -100)


class TestReservation:
    def test_create_reservation_happy_path(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        res_id, order = service.create_reservation("sku-001", 10, "idempotent-key-1")
        assert res_id is not None
        assert order.quantity == 10
        assert order.status == "pending"

        inv = service.repo.get_inventory("sku-001")
        assert inv.quantity == 100
        assert inv.reserved == 10
        assert inv.quantity - inv.reserved == 90

    def test_create_reservation_insufficient_stock(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 50)

        with pytest.raises(ValidationError, match="Insufficient stock"):
            service.create_reservation("sku-001", 100, "idempotent-key-1")

    def test_create_reservation_idempotency(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        res_id_1, order_1 = service.create_reservation("sku-001", 10, "idempotent-key-1")
        res_id_2, order_2 = service.create_reservation("sku-001", 10, "idempotent-key-1")

        assert res_id_1 == res_id_2
        assert order_1.id == order_2.id
        inv = service.repo.get_inventory("sku-001")
        assert inv.reserved == 10

    def test_confirm_reservation(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        res_id, _ = service.create_reservation("sku-001", 10, "idempotent-key-1")
        order = service.confirm_reservation(res_id)

        assert order.status == "confirmed"
        res = service.repo.get_reservation(res_id)
        assert res.status == "confirmed"
        assert res.confirmed_at is not None

    def test_cancel_reservation(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        res_id, _ = service.create_reservation("sku-001", 10, "idempotent-key-1")
        order = service.cancel_reservation(res_id)

        assert order.status == "cancelled"
        res = service.repo.get_reservation(res_id)
        assert res.status == "cancelled"
        inv = service.repo.get_inventory("sku-001")
        assert inv.reserved == 0

    def test_cancel_confirmed_reservation_fails(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        res_id, _ = service.create_reservation("sku-001", 10, "idempotent-key-1")
        service.confirm_reservation(res_id)

        with pytest.raises(ValidationError, match="Cannot cancel a confirmed"):
            service.cancel_reservation(res_id)

    def test_confirm_expired_reservation_fails(self, service: CommerceService, test_db: Session):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        res_id, _ = service.create_reservation("sku-001", 10, "idempotent-key-1")

        res = service.repo.get_reservation(res_id)
        res.created_at = datetime.utcnow() - timedelta(minutes=RESERVATION_TTL_MINUTES + 1)
        test_db.commit()

        with pytest.raises(ValidationError, match="expired"):
            service.confirm_reservation(res_id)


class TestOrderLookup:
    def test_list_orders_empty(self, service: CommerceService):
        orders, total = service.list_orders(page=1, size=10)
        assert len(orders) == 0
        assert total == 0

    def test_list_orders_with_pagination(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 1000)

        for i in range(25):
            service.create_reservation("sku-001", 1, f"key-{i}")

        orders_page_1, total = service.list_orders(page=1, size=10)
        orders_page_2, _ = service.list_orders(page=2, size=10)
        orders_page_3, _ = service.list_orders(page=3, size=10)

        assert len(orders_page_1) == 10
        assert len(orders_page_2) == 10
        assert len(orders_page_3) == 5
        assert total == 25

    def test_get_order(self, service: CommerceService):
        service.create_sku("sku-001", "Widget A")
        service.adjust_stock("sku-001", 100)

        _, order = service.create_reservation("sku-001", 10, "idempotent-key-1")
        retrieved = service.get_order(order.id)

        assert retrieved.id == order.id
        assert retrieved.quantity == 10

    def test_get_nonexistent_order_fails(self, service: CommerceService):
        with pytest.raises(NotFoundError):
            service.get_order("nonexistent-order-id")
