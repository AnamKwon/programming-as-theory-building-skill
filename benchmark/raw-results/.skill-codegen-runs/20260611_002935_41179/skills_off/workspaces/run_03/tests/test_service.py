import pytest
import os
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.repository import Base, Repository
from src.commerce_service.service import CommerceService, RESERVATION_EXPIRY_SECONDS


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    db_fd, db_path = tempfile.mkstemp()
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    yield SessionLocal

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def repository(test_db):
    """Create a repository instance."""
    session = test_db()
    yield Repository(session)
    session.close()


@pytest.fixture
def service(repository):
    """Create a service instance."""
    return CommerceService(repository)


class TestCreateSKU:
    def test_create_sku_success(self, service):
        """Test creating a new SKU."""
        sku = service.create_sku("SKU001", 100)
        assert sku.sku == "SKU001"
        assert sku.available_stock == 100

    def test_create_duplicate_sku_fails(self, service):
        """Test that creating duplicate SKU fails."""
        service.create_sku("SKU001", 100)
        with pytest.raises(Exception):  # HTTPException
            service.create_sku("SKU001", 50)


class TestAdjustStock:
    def test_adjust_stock_positive(self, service):
        """Test increasing stock."""
        service.create_sku("SKU001", 100)
        sku = service.adjust_stock("SKU001", 50)
        assert sku.available_stock == 150

    def test_adjust_stock_negative(self, service):
        """Test decreasing stock."""
        service.create_sku("SKU001", 100)
        sku = service.adjust_stock("SKU001", -30)
        assert sku.available_stock == 70

    def test_adjust_stock_nonexistent_sku(self, service):
        """Test adjusting stock for non-existent SKU."""
        with pytest.raises(Exception):  # HTTPException
            service.adjust_stock("NONEXISTENT", 10)


class TestCreateReservation:
    def test_create_reservation_success(self, service):
        """Test creating a valid reservation."""
        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 30, "idempotency-1")

        assert reservation.sku == "SKU001"
        assert reservation.quantity == 30
        assert reservation.status == "PENDING"
        assert reservation.idempotency_key == "idempotency-1"

        # Verify stock was deducted
        sku = service.repository.get_sku_by_name("SKU001")
        assert sku.available_stock == 70

    def test_create_reservation_insufficient_stock(self, service):
        """Test reservation fails when stock is insufficient."""
        service.create_sku("SKU001", 20)
        with pytest.raises(Exception) as exc:
            service.create_reservation("SKU001", 30, "idempotency-1")
        assert "Insufficient stock" in exc.value.detail

    def test_create_reservation_idempotency(self, service):
        """Test idempotency: same key returns same reservation."""
        service.create_sku("SKU001", 100)

        res1 = service.create_reservation("SKU001", 30, "idempotency-1")
        stock_after_first = service.repository.get_sku_by_name("SKU001").available_stock

        res2 = service.create_reservation("SKU001", 30, "idempotency-1")
        stock_after_second = service.repository.get_sku_by_name("SKU001").available_stock

        assert res1.id == res2.id
        assert stock_after_first == stock_after_second == 70

    def test_create_reservation_nonexistent_sku(self, service):
        """Test reservation for non-existent SKU fails."""
        with pytest.raises(Exception):  # HTTPException
            service.create_reservation("NONEXISTENT", 10, "idempotency-1")


class TestConfirmReservation:
    def test_confirm_reservation_success(self, service):
        """Test confirming a reservation."""
        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 30, "idempotency-1")

        confirmed, order = service.confirm_reservation(reservation.id)

        assert confirmed.status == "CONFIRMED"
        assert order.reservation_id == reservation.id

    def test_confirm_reservation_already_confirmed(self, service):
        """Test confirming an already confirmed reservation fails."""
        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 30, "idempotency-1")
        service.confirm_reservation(reservation.id)

        with pytest.raises(Exception):  # HTTPException
            service.confirm_reservation(reservation.id)

    def test_confirm_reservation_expired(self, service, repository):
        """Test confirming an expired reservation."""
        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 30, "idempotency-1")

        # Manually update created_at to simulate expiration
        past_time = datetime.utcnow() - timedelta(seconds=RESERVATION_EXPIRY_SECONDS + 10)
        db_reservation = repository.get_reservation(reservation.id)
        db_reservation.created_at = past_time
        repository.commit()

        with pytest.raises(Exception) as exc:
            service.confirm_reservation(reservation.id)
        assert "expired" in exc.value.detail

        # Verify stock was restored
        sku = service.repository.get_sku_by_name("SKU001")
        assert sku.available_stock == 100

    def test_confirm_nonexistent_reservation(self, service):
        """Test confirming non-existent reservation."""
        with pytest.raises(Exception):  # HTTPException
            service.confirm_reservation(999)


class TestCancelReservation:
    def test_cancel_reservation_success(self, service):
        """Test cancelling a reservation."""
        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 30, "idempotency-1")

        cancelled = service.cancel_reservation(reservation.id)

        assert cancelled.status == "CANCELLED"

        # Verify stock was restored
        sku = service.repository.get_sku_by_name("SKU001")
        assert sku.available_stock == 100

    def test_cancel_already_confirmed_reservation(self, service):
        """Test cancelling a confirmed reservation fails."""
        service.create_sku("SKU001", 100)
        reservation = service.create_reservation("SKU001", 30, "idempotency-1")
        service.confirm_reservation(reservation.id)

        with pytest.raises(Exception):  # HTTPException
            service.cancel_reservation(reservation.id)

    def test_cancel_nonexistent_reservation(self, service):
        """Test cancelling non-existent reservation."""
        with pytest.raises(Exception):  # HTTPException
            service.cancel_reservation(999)


class TestGetOrders:
    def test_get_orders_pagination(self, service):
        """Test order pagination."""
        service.create_sku("SKU001", 1000)

        # Create and confirm multiple reservations
        for i in range(5):
            res = service.create_reservation(f"SKU001", 10, f"key-{i}")
            service.confirm_reservation(res.id)

        orders, total = service.get_orders(page=1, size=2)
        assert len(orders) == 2
        assert total == 5

    def test_get_orders_second_page(self, service):
        """Test getting second page of orders."""
        service.create_sku("SKU001", 1000)

        for i in range(5):
            res = service.create_reservation(f"SKU001", 10, f"key-{i}")
            service.confirm_reservation(res.id)

        orders, total = service.get_orders(page=2, size=2)
        assert len(orders) == 2
        assert total == 5

    def test_get_orders_empty(self, service):
        """Test getting orders when none exist."""
        orders, total = service.get_orders()
        assert len(orders) == 0
        assert total == 0
