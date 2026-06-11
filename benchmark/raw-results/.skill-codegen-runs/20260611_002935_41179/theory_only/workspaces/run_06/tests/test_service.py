"""Service layer tests."""

import pytest
import time
from datetime import datetime, timedelta

from src.commerce_service.repository import Repository
from src.commerce_service.service import CommercService
from src.commerce_service.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def repository(test_db):
    """Create a repository with test database."""
    repo = Repository("sqlite:///:memory:")
    return repo


@pytest.fixture
def service(repository):
    """Create a service with test repository."""
    return CommercService(repository)


def test_create_sku(service):
    """Test creating a SKU."""
    sku = service.create_sku("TEST-SKU-001", 100)
    assert sku.sku == "TEST-SKU-001"
    assert sku.stock == 100


def test_adjust_stock_increase(service):
    """Test increasing stock."""
    service.create_sku("TEST-SKU-002", 50)
    new_stock = service.adjust_stock("TEST-SKU-002", 25)
    assert new_stock == 75


def test_adjust_stock_decrease(service):
    """Test decreasing stock."""
    service.create_sku("TEST-SKU-003", 100)
    new_stock = service.adjust_stock("TEST-SKU-003", -30)
    assert new_stock == 70


def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("TEST-SKU-004", 100)
    reservation, is_new = service.create_reservation("TEST-SKU-004", 20, "key-001")
    assert is_new is True
    assert reservation.status == "PENDING"
    assert reservation.quantity == 20
    assert reservation.sku == "TEST-SKU-004"


def test_create_reservation_deducts_stock(service):
    """Test that reservation creation deducts stock."""
    service.create_sku("TEST-SKU-005", 100)
    service.create_reservation("TEST-SKU-005", 30, "key-002")
    sku = service.repo.get_sku_by_name("TEST-SKU-005")
    assert sku.stock == 70


def test_create_reservation_insufficient_stock(service):
    """Test reservation fails with insufficient stock."""
    service.create_sku("TEST-SKU-006", 50)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("TEST-SKU-006", 100, "key-003")


def test_reservation_idempotency(service):
    """Test idempotent reservation creation."""
    service.create_sku("TEST-SKU-007", 100)
    res1, is_new_1 = service.create_reservation("TEST-SKU-007", 25, "key-004")
    res2, is_new_2 = service.create_reservation("TEST-SKU-007", 25, "key-004")

    assert is_new_1 is True
    assert is_new_2 is False
    assert res1.id == res2.id
    assert res1.quantity == res2.quantity

    sku = service.repo.get_sku_by_name("TEST-SKU-007")
    assert sku.stock == 75


def test_confirm_reservation_success(service):
    """Test confirming a reservation."""
    service.create_sku("TEST-SKU-008", 100)
    res, _ = service.create_reservation("TEST-SKU-008", 20, "key-005")

    confirmed, order = service.confirm_reservation(res.id)

    assert confirmed.status == "CONFIRMED"
    assert order.id is not None
    assert order.reservation_id == res.id


def test_confirm_non_pending_reservation(service):
    """Test confirming a non-pending reservation fails."""
    service.create_sku("TEST-SKU-009", 100)
    res, _ = service.create_reservation("TEST-SKU-009", 20, "key-006")
    service.confirm_reservation(res.id)

    with pytest.raises(ValueError, match="Cannot confirm"):
        service.confirm_reservation(res.id)


def test_cancel_reservation_success(service):
    """Test cancelling a reservation."""
    service.create_sku("TEST-SKU-010", 100)
    res, _ = service.create_reservation("TEST-SKU-010", 30, "key-007")

    sku_before = service.repo.get_sku_by_name("TEST-SKU-010")
    assert sku_before.stock == 70

    cancelled = service.cancel_reservation(res.id)

    assert cancelled.status == "CANCELLED"

    sku_after = service.repo.get_sku_by_name("TEST-SKU-010")
    assert sku_after.stock == 100


def test_cancel_non_pending_reservation(service):
    """Test cancelling a non-pending reservation fails."""
    service.create_sku("TEST-SKU-011", 100)
    res, _ = service.create_reservation("TEST-SKU-011", 20, "key-008")
    service.confirm_reservation(res.id)

    with pytest.raises(ValueError, match="Cannot cancel"):
        service.cancel_reservation(res.id)


def test_reservation_expiration(service):
    """Test that old reservations cannot be confirmed."""
    service.create_sku("TEST-SKU-012", 100)
    res, _ = service.create_reservation("TEST-SKU-012", 40, "key-009")

    reservation = service.repo.get_reservation_by_id(res.id)
    reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
    session = service.repo.get_session()
    try:
        session.merge(reservation)
        session.commit()
    finally:
        session.close()

    with pytest.raises(ValueError, match="Reservation expired"):
        service.confirm_reservation(res.id)

    expired_res = service.repo.get_reservation_by_id(res.id)
    assert expired_res.status == "EXPIRED"

    sku = service.repo.get_sku_by_name("TEST-SKU-012")
    assert sku.stock == 100


def test_get_orders_paginated(service):
    """Test pagination on orders."""
    service.create_sku("TEST-SKU-013", 500)

    for i in range(25):
        res, _ = service.create_reservation("TEST-SKU-013", 5, f"key-{1000+i}")
        service.confirm_reservation(res.id)

    page1, total1 = service.get_orders_paginated(page=1, size=10)
    assert len(page1) == 10
    assert total1 == 25

    page2, total2 = service.get_orders_paginated(page=2, size=10)
    assert len(page2) == 10
    assert total2 == 25

    page3, total3 = service.get_orders_paginated(page=3, size=10)
    assert len(page3) == 5
    assert total3 == 25
