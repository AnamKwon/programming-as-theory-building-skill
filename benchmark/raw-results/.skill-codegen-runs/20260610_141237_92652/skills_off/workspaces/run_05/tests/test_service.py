import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base, CreateSKURequest, AdjustStockRequest, CreateReservationRequest
from src.commerce_service.service import CommerceService
from src.commerce_service.repository import Repository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    return CommerceService(db_session)


class TestSKUManagement:
    def test_create_sku(self, service):
        request = CreateSKURequest(sku="TEST-SKU-001", initial_stock=100)
        sku = service.create_sku(request)
        assert sku.sku == "TEST-SKU-001"
        assert sku.available_stock == 100

    def test_adjust_stock_positive(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-002", initial_stock=50))
        result = service.adjust_stock(AdjustStockRequest(sku="TEST-SKU-002", amount=25))
        assert result["available_stock"] == 75

    def test_adjust_stock_negative(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-003", initial_stock=50))
        result = service.adjust_stock(AdjustStockRequest(sku="TEST-SKU-003", amount=-10))
        assert result["available_stock"] == 40

    def test_adjust_stock_nonexistent_sku(self, service):
        with pytest.raises(ValueError, match="SKU .* not found"):
            service.adjust_stock(AdjustStockRequest(sku="NONEXISTENT", amount=10))


class TestReservations:
    def test_create_reservation_happy_path(self, service, db_session):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-004", initial_stock=100))
        request = CreateReservationRequest(sku="TEST-SKU-004", quantity=30, idempotency_key="idem-001")
        reservation = service.create_reservation(request)

        assert reservation.sku == "TEST-SKU-004"
        assert reservation.quantity == 30
        assert reservation.status == "PENDING"

        sku = service.repo.get_sku_by_code("TEST-SKU-004")
        assert sku.available_stock == 70

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-005", initial_stock=20))
        request = CreateReservationRequest(sku="TEST-SKU-005", quantity=30, idempotency_key="idem-002")

        with pytest.raises(ValueError, match="Insufficient stock"):
            service.create_reservation(request)

    def test_create_reservation_idempotency(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-006", initial_stock=100))
        request = CreateReservationRequest(sku="TEST-SKU-006", quantity=25, idempotency_key="idem-003")

        reservation1 = service.create_reservation(request)
        reservation2 = service.create_reservation(request)

        assert reservation1.id == reservation2.id
        assert reservation1.created_at == reservation2.created_at

        sku = service.repo.get_sku_by_code("TEST-SKU-006")
        assert sku.available_stock == 75

    def test_create_reservation_nonexistent_sku(self, service):
        request = CreateReservationRequest(sku="NONEXISTENT", quantity=10, idempotency_key="idem-004")
        with pytest.raises(ValueError, match="SKU .* not found"):
            service.create_reservation(request)


class TestConfirmReservation:
    def test_confirm_reservation_happy_path(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-007", initial_stock=100))
        reservation = service.create_reservation(
            CreateReservationRequest(sku="TEST-SKU-007", quantity=20, idempotency_key="idem-005")
        )

        order = service.confirm_reservation(reservation.id)
        assert order.sku == "TEST-SKU-007"
        assert order.quantity == 20
        assert order.reservation_id == reservation.id

        updated_reservation = service.repo.get_reservation_by_id(reservation.id)
        assert updated_reservation.status == "CONFIRMED"

    def test_confirm_reservation_not_pending(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-008", initial_stock=100))
        reservation = service.create_reservation(
            CreateReservationRequest(sku="TEST-SKU-008", quantity=20, idempotency_key="idem-006")
        )

        service.confirm_reservation(reservation.id)

        with pytest.raises(ValueError, match="not in PENDING"):
            service.confirm_reservation(reservation.id)

    def test_confirm_reservation_expired(self, service, db_session):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-009", initial_stock=100))
        reservation = service.create_reservation(
            CreateReservationRequest(sku="TEST-SKU-009", quantity=20, idempotency_key="idem-007")
        )

        # Manually set created_at to 301 seconds ago
        reservation_model = service.repo.get_reservation_by_id(reservation.id)
        reservation_model.created_at = datetime.utcnow() - timedelta(seconds=301)
        db_session.commit()

        with pytest.raises(ValueError, match="expired"):
            service.confirm_reservation(reservation.id)

        updated = service.repo.get_reservation_by_id(reservation.id)
        assert updated.status == "EXPIRED"

        sku = service.repo.get_sku_by_code("TEST-SKU-009")
        assert sku.available_stock == 100

    def test_confirm_nonexistent_reservation(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.confirm_reservation(9999)


class TestCancelReservation:
    def test_cancel_reservation_happy_path(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-010", initial_stock=100))
        reservation = service.create_reservation(
            CreateReservationRequest(sku="TEST-SKU-010", quantity=15, idempotency_key="idem-008")
        )

        sku_before = service.repo.get_sku_by_code("TEST-SKU-010")
        assert sku_before.available_stock == 85

        cancelled = service.cancel_reservation(reservation.id)
        assert cancelled.status == "CANCELLED"

        sku_after = service.repo.get_sku_by_code("TEST-SKU-010")
        assert sku_after.available_stock == 100

    def test_cancel_reservation_not_pending(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-011", initial_stock=100))
        reservation = service.create_reservation(
            CreateReservationRequest(sku="TEST-SKU-011", quantity=20, idempotency_key="idem-009")
        )

        service.confirm_reservation(reservation.id)

        with pytest.raises(ValueError, match="not in PENDING"):
            service.cancel_reservation(reservation.id)

    def test_cancel_nonexistent_reservation(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.cancel_reservation(9999)


class TestOrders:
    def test_get_orders_pagination(self, service):
        service.create_sku(CreateSKURequest(sku="TEST-SKU-012", initial_stock=1000))

        for i in range(25):
            reservation = service.create_reservation(
                CreateReservationRequest(
                    sku="TEST-SKU-012", quantity=10, idempotency_key=f"idem-{1000 + i}"
                )
            )
            service.confirm_reservation(reservation.id)

        page1 = service.get_orders(page=1, size=10)
        assert page1.total == 25
        assert page1.page == 1
        assert page1.size == 10
        assert len(page1.items) == 10

        page2 = service.get_orders(page=2, size=10)
        assert len(page2.items) == 10

        page3 = service.get_orders(page=3, size=10)
        assert len(page3.items) == 5

    def test_get_orders_empty(self, service):
        result = service.get_orders(page=1, size=10)
        assert result.total == 0
        assert len(result.items) == 0


class TestWorkflow:
    def test_complete_workflow(self, service):
        service.create_sku(CreateSKURequest(sku="PRODUCT-A", initial_stock=100))

        reservation = service.create_reservation(
            CreateReservationRequest(sku="PRODUCT-A", quantity=25, idempotency_key="order-001")
        )
        assert reservation.status == "PENDING"

        order = service.confirm_reservation(reservation.id)
        assert order.reservation_id == reservation.id

        orders = service.get_orders(page=1, size=10)
        assert orders.total == 1
        assert orders.items[0].id == order.id

        sku = service.repo.get_sku_by_code("PRODUCT-A")
        assert sku.available_stock == 75
