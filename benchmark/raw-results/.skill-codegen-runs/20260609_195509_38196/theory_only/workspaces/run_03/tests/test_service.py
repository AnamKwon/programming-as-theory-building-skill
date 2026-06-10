"""Tests for the service business logic layer."""
import pytest
from datetime import datetime, timedelta

from src.commerce_service.repository import Repository
from src.commerce_service.service import (
    Service,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def repo():
    """In-memory SQLite repository for testing."""
    return Repository("sqlite:///:memory:")


@pytest.fixture
def service(repo):
    """Service instance with test repository."""
    return Service(repo)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("WIDGET-001", "Blue Widget")
    assert result["sku"] == "WIDGET-001"
    assert result["name"] == "Blue Widget"
    assert result["id"] is not None


def test_adjust_stock_positive(service):
    """Test adding stock."""
    service.create_sku("WIDGET-001", "Blue Widget")
    result = service.adjust_stock("WIDGET-001", 100)
    assert result["available"] == 100
    assert result["reserved"] == 0


def test_adjust_stock_negative(service):
    """Test removing stock."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)
    result = service.adjust_stock("WIDGET-001", -30)
    assert result["available"] == 70


def test_adjust_stock_nonexistent_sku(service):
    """Test adjustment on non-existent SKU raises error."""
    with pytest.raises(Exception, match="not found"):
        service.adjust_stock("NONEXISTENT", 100)


def test_reserve_happy_path(service):
    """Test successful reservation."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    result = service.reserve("WIDGET-001", 5, "order-123")
    assert result["id"] is not None
    assert result["quantity"] == 5
    assert result["state"] == "pending"


def test_reserve_insufficient_stock(service):
    """Test reservation fails with insufficient stock."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 3)

    with pytest.raises(InsufficientStockError):
        service.reserve("WIDGET-001", 5, "order-123")


def test_reserve_idempotent(service):
    """Test idempotency: same key returns error on retry."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    result1 = service.reserve("WIDGET-001", 5, "order-123")
    with pytest.raises(Exception, match="already used"):
        service.reserve("WIDGET-001", 5, "order-123")


def test_confirm_reservation_happy_path(service):
    """Test confirming a pending reservation."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    res = service.reserve("WIDGET-001", 5, "order-123")
    result = service.confirm_reservation(res["id"])

    assert result["state"] == "confirmed"
    assert result["order_id"] is not None


def test_confirm_nonexistent_reservation(service):
    """Test confirming non-existent reservation raises error."""
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation(999)


def test_confirm_expired_reservation(service, repo):
    """Test confirming an expired reservation raises error."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    res = service.reserve("WIDGET-001", 5, "order-123")

    # Manually expire the reservation in the database
    reservation = repo.get_reservation(res["id"])
    reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    session = repo._get_session()
    session.merge(reservation)
    session.commit()
    session.close()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(res["id"])


def test_confirm_already_confirmed_reservation(service):
    """Test confirming an already-confirmed reservation raises error."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    res = service.reserve("WIDGET-001", 5, "order-123")
    service.confirm_reservation(res["id"])

    with pytest.raises(InvalidStateTransitionError):
        service.confirm_reservation(res["id"])


def test_cancel_reservation_happy_path(service):
    """Test canceling a pending reservation."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    res = service.reserve("WIDGET-001", 5, "order-123")
    result = service.cancel_reservation(res["id"])

    assert result["state"] == "cancelled"


def test_cancel_nonexistent_reservation(service):
    """Test canceling non-existent reservation raises error."""
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation(999)


def test_cancel_confirmed_reservation(service):
    """Test canceling a confirmed reservation raises error."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    res = service.reserve("WIDGET-001", 5, "order-123")
    service.confirm_reservation(res["id"])

    with pytest.raises(InvalidStateTransitionError):
        service.cancel_reservation(res["id"])


def test_lookup_orders_empty(service):
    """Test looking up orders when empty."""
    result = service.lookup_orders()
    assert result["total"] == 0
    assert result["orders"] == []
    assert result["has_next"] is False


def test_lookup_orders_with_pagination(service):
    """Test order pagination."""
    service.create_sku("WIDGET-001", "Blue Widget")
    service.adjust_stock("WIDGET-001", 100)

    for i in range(15):
        res = service.reserve("WIDGET-001", 1, f"order-{i}")
        service.confirm_reservation(res["id"])

    page1 = service.lookup_orders(page=1, page_size=10)
    assert len(page1["orders"]) == 10
    assert page1["total"] == 15
    assert page1["has_next"] is True

    page2 = service.lookup_orders(page=2, page_size=10)
    assert len(page2["orders"]) == 5
    assert page2["has_next"] is False
