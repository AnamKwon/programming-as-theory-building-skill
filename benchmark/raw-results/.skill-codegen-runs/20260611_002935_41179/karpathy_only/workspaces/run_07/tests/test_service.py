"""Service layer tests."""
import pytest
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.repository import Base, Repository
from commerce_service.service import CommerceService, RESERVATION_EXPIRATION_SECONDS


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    """Create a repository instance."""
    return Repository(db_session)


@pytest.fixture
def service(repository):
    """Create a service instance."""
    return CommerceService(repository)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["available_stock"] == 100
    assert result["id"] == 1


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("SKU-002", 50)
    result = service.adjust_stock("SKU-002", 10)
    assert result["available_stock"] == 60

    result = service.adjust_stock("SKU-002", -15)
    assert result["available_stock"] == 45


def test_adjust_stock_sku_not_found(service):
    """Test stock adjustment for non-existent SKU."""
    with pytest.raises(ValueError, match="SKU not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("SKU-003", 100)
    result = service.create_reservation("SKU-003", 20, "key-001")

    assert result.id == 1
    assert result.sku == "SKU-003"
    assert result.quantity == 20
    assert result.status == "PENDING"
    assert result.idempotency_key == "key-001"


def test_create_reservation_insufficient_stock(service):
    """Test reservation creation with insufficient stock."""
    service.create_sku("SKU-004", 10)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-004", 20, "key-002")


def test_create_reservation_sku_not_found(service):
    """Test reservation creation for non-existent SKU."""
    with pytest.raises(ValueError, match="SKU not found"):
        service.create_reservation("NONEXISTENT", 10, "key-003")


def test_reservation_idempotency(service):
    """Test that idempotent reservation returns same result without deducting stock twice."""
    service.create_sku("SKU-005", 100)

    result1 = service.create_reservation("SKU-005", 30, "idempotent-key-1")
    assert result1.id == 1
    assert result1.quantity == 30

    sku_after_first = service.repository.get_sku_by_name("SKU-005")
    assert sku_after_first.available_stock == 70

    result2 = service.create_reservation("SKU-005", 30, "idempotent-key-1")
    assert result2.id == 1
    assert result2.quantity == 30

    sku_after_second = service.repository.get_sku_by_name("SKU-005")
    assert sku_after_second.available_stock == 70


def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    service.create_sku("SKU-006", 100)
    reservation = service.create_reservation("SKU-006", 25, "confirm-key-1")

    result = service.confirm_reservation(reservation.id)
    assert result.status == "CONFIRMED"
    assert result.order_id == 1


def test_confirm_reservation_not_found(service):
    """Test confirmation of non-existent reservation."""
    with pytest.raises(ValueError, match="Reservation not found"):
        service.confirm_reservation(999)


def test_confirm_reservation_not_pending(service):
    """Test confirmation of non-PENDING reservation."""
    service.create_sku("SKU-007", 100)
    reservation = service.create_reservation("SKU-007", 25, "confirm-key-2")

    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING status"):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_expired(service, repository):
    """Test confirmation of expired reservation."""
    service.create_sku("SKU-008", 100)
    reservation = service.create_reservation("SKU-008", 25, "expired-key-1")

    old_reservation = repository.get_reservation_by_id(reservation.id)
    old_reservation.created_at = datetime.utcnow() - timedelta(seconds=RESERVATION_EXPIRATION_SECONDS + 1)
    repository.db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)

    updated = repository.get_reservation_by_id(reservation.id)
    assert updated.status == "EXPIRED"

    sku = repository.get_sku_by_name("SKU-008")
    assert sku.available_stock == 100


def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    service.create_sku("SKU-009", 100)
    reservation = service.create_reservation("SKU-009", 25, "cancel-key-1")

    sku_before = service.repository.get_sku_by_name("SKU-009")
    assert sku_before.available_stock == 75

    result = service.cancel_reservation(reservation.id)
    assert result.status == "CANCELLED"
    assert result.stock_restored == 25

    sku_after = service.repository.get_sku_by_name("SKU-009")
    assert sku_after.available_stock == 100


def test_cancel_reservation_not_found(service):
    """Test cancellation of non-existent reservation."""
    with pytest.raises(ValueError, match="Reservation not found"):
        service.cancel_reservation(999)


def test_cancel_reservation_not_pending(service):
    """Test cancellation of non-PENDING reservation."""
    service.create_sku("SKU-010", 100)
    reservation = service.create_reservation("SKU-010", 25, "cancel-key-2")

    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING status"):
        service.cancel_reservation(reservation.id)


def test_get_orders_paginated(service):
    """Test paginated order retrieval."""
    service.create_sku("SKU-011", 200)

    for i in range(25):
        res = service.create_reservation("SKU-011", 1, f"order-key-{i}")
        service.confirm_reservation(res.id)

    page1 = service.get_orders_paginated(page=1, size=10)
    assert len(page1["orders"]) == 10
    assert page1["page"] == 1
    assert page1["size"] == 10
    assert page1["total"] == 25

    page2 = service.get_orders_paginated(page=2, size=10)
    assert len(page2["orders"]) == 10
    assert page2["page"] == 2

    page3 = service.get_orders_paginated(page=3, size=10)
    assert len(page3["orders"]) == 5
    assert page3["page"] == 3


def test_happy_path_workflow(service):
    """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
    service.create_sku("SKU-HAPPY", 150)

    reservation = service.create_reservation("SKU-HAPPY", 50, "happy-key-1")
    assert reservation.status == "PENDING"

    confirm_result = service.confirm_reservation(reservation.id)
    assert confirm_result.status == "CONFIRMED"
    assert confirm_result.order_id == 1

    orders = service.get_orders_paginated(page=1, size=10)
    assert len(orders["orders"]) == 1
    assert orders["orders"][0]["reservation_id"] == reservation.id
