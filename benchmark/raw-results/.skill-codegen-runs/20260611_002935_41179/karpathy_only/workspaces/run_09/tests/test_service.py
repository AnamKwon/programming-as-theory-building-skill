"""Tests for service layer."""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
    return Service(repository)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("TEST-SKU-001", 100)
    assert result["sku"] == "TEST-SKU-001"
    assert result["initial_stock"] == 100


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("TEST-SKU-002", 50)
    result = service.adjust_stock("TEST-SKU-002", 10)
    assert result["available_stock"] == 60

    result = service.adjust_stock("TEST-SKU-002", -20)
    assert result["available_stock"] == 40


def test_create_reservation_happy_path(service):
    """Test creating a reservation."""
    service.create_sku("TEST-SKU-003", 100)
    result = service.create_reservation("TEST-SKU-003", 10, "idempotency-key-1")

    assert result.id is not None
    assert result.sku == "TEST-SKU-003"
    assert result.quantity == 10
    assert result.status == "PENDING"
    assert result.idempotency_key == "idempotency-key-1"

    sku_model = service.repository.get_sku("TEST-SKU-003")
    assert sku_model.available_stock == 90


def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("TEST-SKU-004", 5)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("TEST-SKU-004", 10, "idempotency-key-2")


def test_create_reservation_idempotency(service):
    """Test reservation idempotency."""
    service.create_sku("TEST-SKU-005", 100)

    result1 = service.create_reservation("TEST-SKU-005", 10, "idempotency-key-3")
    result2 = service.create_reservation("TEST-SKU-005", 20, "idempotency-key-3")

    assert result1.id == result2.id
    assert result1.quantity == result2.quantity
    assert result1.quantity == 10

    sku_model = service.repository.get_sku("TEST-SKU-005")
    assert sku_model.available_stock == 90


def test_confirm_reservation(service):
    """Test confirming a reservation."""
    service.create_sku("TEST-SKU-006", 100)
    reservation = service.create_reservation("TEST-SKU-006", 15, "idempotency-key-4")

    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == "CONFIRMED"

    order = service.repository.db.query(
        __import__("commerce_service.models", fromlist=["OrderModel"]).OrderModel
    ).first()
    assert order is not None
    assert order.reservation_id == reservation.id


def test_confirm_reservation_not_pending(service, repository):
    """Test confirming a non-pending reservation."""
    service.create_sku("TEST-SKU-007", 100)
    reservation = service.create_reservation("TEST-SKU-007", 10, "idempotency-key-5")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not PENDING"):
        service.confirm_reservation(reservation.id)


def test_confirm_reservation_expired(service, repository):
    """Test confirming an expired reservation."""
    service.create_sku("TEST-SKU-008", 100)

    reservation_id = str(uuid.uuid4())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()

    reservation = repository.create_reservation(
        reservation_id=reservation_id,
        sku="TEST-SKU-008",
        quantity=10,
        idempotency_key="idempotency-key-6",
        status="PENDING",
        created_at=old_time,
    )

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation_id)

    updated = repository.get_reservation(reservation_id)
    assert updated.status == "EXPIRED"

    sku_model = repository.get_sku("TEST-SKU-008")
    assert sku_model.available_stock == 100


def test_cancel_reservation(service):
    """Test cancelling a reservation."""
    service.create_sku("TEST-SKU-009", 100)
    reservation = service.create_reservation("TEST-SKU-009", 20, "idempotency-key-7")

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "CANCELLED"

    sku_model = service.repository.get_sku("TEST-SKU-009")
    assert sku_model.available_stock == 100


def test_cancel_reservation_not_pending(service):
    """Test cancelling a non-pending reservation."""
    service.create_sku("TEST-SKU-010", 100)
    reservation = service.create_reservation("TEST-SKU-010", 10, "idempotency-key-8")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not PENDING"):
        service.cancel_reservation(reservation.id)


def test_get_orders_paginated(service):
    """Test paginated orders retrieval."""
    service.create_sku("TEST-SKU-011", 100)

    for i in range(5):
        reservation = service.create_reservation(f"TEST-SKU-011", 10, f"idempotency-key-paginated-{i}")
        service.confirm_reservation(reservation.id)

    result = service.get_orders_paginated(page=1, size=2)
    assert result["total"] == 5
    assert result["page"] == 1
    assert result["size"] == 2
    assert len(result["orders"]) == 2

    result_page2 = service.get_orders_paginated(page=2, size=2)
    assert len(result_page2["orders"]) == 2

    result_page3 = service.get_orders_paginated(page=3, size=2)
    assert len(result_page3["orders"]) == 1
