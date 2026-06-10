"""Unit tests for the service layer."""

import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService
from src.commerce_service.models import (
    SKUCreate,
    StockAdjustRequest,
    ReservationCreate,
)


@pytest.fixture
def repo():
    """Create a temporary SQLite repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db_url = f"sqlite:///{db_path}"
        yield Repository(db_url)


@pytest.fixture
def service(repo):
    """Create a service instance with test repository."""
    return CommerceService(repo)


def test_create_sku(service):
    """Test SKU creation."""
    request = SKUCreate(sku="TEST-SKU", initial_stock=100)
    response = service.create_sku(request)

    assert response.sku == "TEST-SKU"
    assert response.available_stock == 100
    assert response.reserved_stock == 0


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = StockAdjustRequest(sku="TEST-SKU", amount=50)
    response = service.adjust_stock(request)

    assert response.sku == "TEST-SKU"
    assert response.available_stock == 150
    assert response.reserved_stock == 0


def test_adjust_stock_negative(service):
    """Test negative stock adjustment."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = StockAdjustRequest(sku="TEST-SKU", amount=-30)
    response = service.adjust_stock(request)

    assert response.available_stock == 70


def test_create_reservation(service):
    """Test reservation creation (happy path)."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-1")
    response, is_idempotent = service.create_reservation(request)

    assert response.sku == "TEST-SKU"
    assert response.quantity == 50
    assert response.status == "PENDING"
    assert is_idempotent is False


def test_create_reservation_insufficient_stock(service):
    """Test reservation creation with insufficient stock."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=30))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-2")
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation(request)


def test_create_reservation_idempotency(service):
    """Test idempotent reservation creation."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-3")
    response1, is_idempotent1 = service.create_reservation(request)

    response2, is_idempotent2 = service.create_reservation(request)

    assert response1.id == response2.id
    assert is_idempotent1 is False
    assert is_idempotent2 is True


def test_confirm_reservation(service):
    """Test reservation confirmation."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-4")
    res_response, _ = service.create_reservation(request)

    confirm_response = service.confirm_reservation(res_response.id)

    assert confirm_response.id == res_response.id
    assert confirm_response.status == "CONFIRMED"
    assert confirm_response.order_id > 0


def test_confirm_reservation_expired(service, repo):
    """Test confirmation of expired reservation."""
    from src.commerce_service.repository import ReservationRecord

    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-5")
    res_response, _ = service.create_reservation(request)

    session = repo.get_session()
    reservation = session.query(ReservationRecord).filter(ReservationRecord.id == res_response.id).first()
    past_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=301)
    reservation.created_at = past_time
    session.commit()
    session.close()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res_response.id)

    expired_reservation = repo.get_reservation(res_response.id)
    assert expired_reservation.status == "EXPIRED"


def test_confirm_reservation_invalid_state(service):
    """Test confirmation of reservation in invalid state."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-6")
    res_response, _ = service.create_reservation(request)

    service.cancel_reservation(res_response.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(res_response.id)


def test_cancel_reservation(service):
    """Test reservation cancellation."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=100))

    request = ReservationCreate(sku="TEST-SKU", quantity=50, idempotency_key="unique-key-7")
    res_response, _ = service.create_reservation(request)

    sku_before = service.repo.get_sku("TEST-SKU")
    assert sku_before.available_stock == 50
    assert sku_before.reserved_stock == 50

    cancel_response = service.cancel_reservation(res_response.id)

    assert cancel_response.status == "CANCELLED"

    sku_after = service.repo.get_sku("TEST-SKU")
    assert sku_after.available_stock == 100
    assert sku_after.reserved_stock == 0


def test_get_orders_pagination(service):
    """Test orders list with pagination."""
    service.create_sku(SKUCreate(sku="TEST-SKU", initial_stock=1000))

    for i in range(15):
        request = ReservationCreate(sku="TEST-SKU", quantity=10, idempotency_key=f"unique-key-{100+i}")
        res_response, _ = service.create_reservation(request)
        service.confirm_reservation(res_response.id)

    response_page1 = service.get_orders(page=1, size=10)
    assert len(response_page1.items) == 10
    assert response_page1.total == 15
    assert response_page1.page == 1
    assert response_page1.size == 10

    response_page2 = service.get_orders(page=2, size=10)
    assert len(response_page2.items) == 5
    assert response_page2.page == 2
