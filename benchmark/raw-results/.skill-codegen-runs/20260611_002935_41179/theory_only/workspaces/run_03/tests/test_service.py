"""Service layer tests."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from commerce_service.models import Base, CreateReservationRequest, CreateSKURequest
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    """Create test database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db):
    """Create service instance."""
    return CommerceService(db)


class TestSKUCreation:
    """Tests for SKU creation."""

    def test_create_sku_success(self, service):
        """Test successful SKU creation."""
        request = CreateSKURequest(sku="TEST-001", initial_stock=100)
        response = service.create_sku(request)

        assert response.sku == "TEST-001"
        assert response.total_stock == 100
        assert response.available_stock == 100
        assert response.reserved_stock == 0

    def test_create_sku_with_zero_stock(self, service):
        """Test SKU creation with zero initial stock."""
        request = CreateSKURequest(sku="TEST-002", initial_stock=0)
        response = service.create_sku(request)

        assert response.total_stock == 0
        assert response.available_stock == 0


class TestStockAdjustment:
    """Tests for stock adjustment."""

    def test_adjust_stock_increase(self, service):
        """Test increasing stock."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        response = service.adjust_stock("TEST-001", 50)

        assert response.total_stock == 150
        assert response.available_stock == 150

    def test_adjust_stock_decrease(self, service):
        """Test decreasing stock."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        response = service.adjust_stock("TEST-001", -30)

        assert response.total_stock == 70
        assert response.available_stock == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for nonexistent SKU."""
        with pytest.raises(Exception):
            service.adjust_stock("NONEXISTENT", 10)


class TestReservations:
    """Tests for reservation operations."""

    def test_create_reservation_success(self, service):
        """Test successful reservation creation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        response = service.create_reservation(request)

        assert response.sku == "TEST-001"
        assert response.quantity == 50
        assert response.status == "PENDING"
        assert response.idempotency_key == "KEY-001"

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation with insufficient stock."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=30))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )

        with pytest.raises(Exception) as exc_info:
            service.create_reservation(request)
        assert "Insufficient stock" in str(exc_info.value)

    def test_idempotent_reservation(self, service):
        """Test idempotent reservation creation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )

        response1 = service.create_reservation(request)
        response2 = service.create_reservation(request)

        assert response1.id == response2.id
        assert response1.quantity == response2.quantity

    def test_reservation_stock_deduction(self, service):
        """Test that reservation deducts from available stock."""
        sku_response = service.create_sku(
            CreateSKURequest(sku="TEST-001", initial_stock=100)
        )
        initial_available = sku_response.available_stock

        request = CreateReservationRequest(
            sku="TEST-001", quantity=30, idempotency_key="KEY-001"
        )
        service.create_reservation(request)

        # Check by creating another reservation
        request2 = CreateReservationRequest(
            sku="TEST-001", quantity=71, idempotency_key="KEY-002"
        )
        with pytest.raises(Exception) as exc_info:
            service.create_reservation(request2)
        assert "Insufficient stock" in str(exc_info.value)


class TestReservationConfirmation:
    """Tests for reservation confirmation."""

    def test_confirm_reservation_success(self, service):
        """Test successful reservation confirmation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        response = service.confirm_reservation(reservation.id)
        assert response.status == "CONFIRMED"

    def test_confirm_nonexistent_reservation(self, service):
        """Test confirming nonexistent reservation."""
        with pytest.raises(Exception):
            service.confirm_reservation(999)

    def test_confirm_non_pending_reservation(self, service):
        """Test confirming already confirmed reservation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        service.confirm_reservation(reservation.id)

        with pytest.raises(Exception) as exc_info:
            service.confirm_reservation(reservation.id)
        assert "Cannot confirm" in str(exc_info.value)

    def test_confirm_expired_reservation(self, service, db):
        """Test confirming expired reservation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        # Manually set created_at to 301 seconds ago
        from commerce_service.models import ReservationModel
        res = db.query(ReservationModel).filter(
            ReservationModel.id == reservation.id
        ).first()
        res.created_at = datetime.utcnow() - timedelta(seconds=301)
        db.commit()

        with pytest.raises(Exception) as exc_info:
            service.confirm_reservation(reservation.id)
        assert "expired" in str(exc_info.value).lower()

    def test_expired_reservation_restores_stock(self, service, db):
        """Test that expired reservation restores stock."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        # Manually set created_at to 301 seconds ago
        from commerce_service.models import ReservationModel
        res = db.query(ReservationModel).filter(
            ReservationModel.id == reservation.id
        ).first()
        res.created_at = datetime.utcnow() - timedelta(seconds=301)
        db.commit()

        with pytest.raises(Exception):
            service.confirm_reservation(reservation.id)

        # Check that stock was restored
        from commerce_service.models import SKUModel
        sku = db.query(SKUModel).filter(SKUModel.sku == "TEST-001").first()
        assert sku.available_stock == 100


class TestReservationCancellation:
    """Tests for reservation cancellation."""

    def test_cancel_reservation_success(self, service):
        """Test successful reservation cancellation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        response = service.cancel_reservation(reservation.id)
        assert response.status == "CANCELLED"

    def test_cancel_restores_stock(self, service, db):
        """Test that cancellation restores stock."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        from commerce_service.models import SKUModel
        sku_before = db.query(SKUModel).filter(SKUModel.sku == "TEST-001").first()
        assert sku_before.available_stock == 50

        service.cancel_reservation(reservation.id)

        sku_after = db.query(SKUModel).filter(SKUModel.sku == "TEST-001").first()
        assert sku_after.available_stock == 100

    def test_cancel_non_pending_reservation(self, service):
        """Test cancelling non-pending reservation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        service.confirm_reservation(reservation.id)

        with pytest.raises(Exception) as exc_info:
            service.cancel_reservation(reservation.id)
        assert "Cannot cancel" in str(exc_info.value)


class TestOrders:
    """Tests for order operations."""

    def test_create_order_on_confirmation(self, service, db):
        """Test that order is created on reservation confirmation."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=100))
        request = CreateReservationRequest(
            sku="TEST-001", quantity=50, idempotency_key="KEY-001"
        )
        reservation = service.create_reservation(request)

        service.confirm_reservation(reservation.id)

        from commerce_service.models import OrderModel
        orders = db.query(OrderModel).all()
        assert len(orders) == 1
        assert orders[0].reservation_id == reservation.id

    def test_get_orders_pagination(self, service):
        """Test order pagination."""
        service.create_sku(CreateSKURequest(sku="TEST-001", initial_stock=500))

        # Create multiple orders
        for i in range(25):
            request = CreateReservationRequest(
                sku="TEST-001", quantity=5, idempotency_key=f"KEY-{i:03d}"
            )
            reservation = service.create_reservation(request)
            service.confirm_reservation(reservation.id)

        # Test pagination
        result = service.get_orders(page=1, size=10)
        assert len(result["orders"]) == 10
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 25

        result = service.get_orders(page=2, size=10)
        assert len(result["orders"]) == 10
        assert result["page"] == 2

        result = service.get_orders(page=3, size=10)
        assert len(result["orders"]) == 5
