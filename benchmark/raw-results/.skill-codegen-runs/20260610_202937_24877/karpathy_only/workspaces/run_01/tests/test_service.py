"""Service layer business logic tests."""

import pytest
import tempfile
import os
from datetime import datetime, timedelta

from src.commerce_service.repository import Repository, Reservation
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db_url = f"sqlite:///{db_path}"
    yield db_url
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def repository(temp_db):
    """Create a repository instance with temp database."""
    return Repository(temp_db)


@pytest.fixture
def service(repository):
    """Create a service instance with temp repository."""
    return CommerceService(repository)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("SKU-001", 100)
    assert result["sku"] == "SKU-001"
    assert result["stock"] == 100


def test_adjust_stock_positive(service):
    """Test positive stock adjustment."""
    service.create_sku("SKU-002", 50)
    result = service.adjust_stock("SKU-002", 30)
    assert result["stock"] == 80


def test_adjust_stock_negative(service):
    """Test negative stock adjustment."""
    service.create_sku("SKU-003", 100)
    result = service.adjust_stock("SKU-003", -25)
    assert result["stock"] == 75


def test_insufficient_stock_error(service):
    """Test that insufficient stock raises error."""
    service.create_sku("SKU-004", 10)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("SKU-004", 20, "key-001")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in str(exc_info.value.detail)


def test_reservation_stock_deduction(service):
    """Test that reservation deducts stock."""
    service.create_sku("SKU-005", 100)
    service.create_reservation("SKU-005", 30, "key-002")
    stock = service.repo.get_sku_stock("SKU-005")
    assert stock == 70


def test_idempotent_reservation_no_double_deduction(service):
    """Test that idempotent reservation doesn't double-deduct stock."""
    service.create_sku("SKU-006", 100)

    res1 = service.create_reservation("SKU-006", 40, "key-003")
    res2 = service.create_reservation("SKU-006", 40, "key-003")

    assert res1["id"] == res2["id"]
    stock = service.repo.get_sku_stock("SKU-006")
    assert stock == 60  # Deducted only once


def test_confirm_reservation(service):
    """Test confirming a reservation."""
    service.create_sku("SKU-007", 100)
    res = service.create_reservation("SKU-007", 20, "key-004")
    reservation_id = res["id"]

    order = service.confirm_reservation(reservation_id)
    assert order["reservation_id"] == reservation_id


def test_confirm_non_pending_reservation(service):
    """Test that confirming non-PENDING reservation fails."""
    service.create_sku("SKU-008", 100)
    res = service.create_reservation("SKU-008", 20, "key-005")
    reservation_id = res["id"]

    service.confirm_reservation(reservation_id)  # First confirm succeeds

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation_id)  # Second should fail
    assert exc_info.value.status_code == 400


def test_expired_reservation_rejection(service, repository):
    """Test that expired reservation cannot be confirmed."""
    service.create_sku("SKU-009", 100)
    res = service.create_reservation("SKU-009", 25, "key-006")
    reservation_id = res["id"]

    # Manually make the reservation old
    session = repository.get_session()
    try:
        reservation = session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
        session.commit()
    finally:
        session.close()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(reservation_id)
    assert exc_info.value.status_code == 400
    assert "expired" in str(exc_info.value.detail).lower()


def test_expired_reservation_restores_stock(service, repository):
    """Test that expired reservation restores stock."""
    service.create_sku("SKU-010", 100)
    res = service.create_reservation("SKU-010", 25, "key-007")
    reservation_id = res["id"]
    initial_stock = repository.get_sku_stock("SKU-010")
    assert initial_stock == 75  # 100 - 25

    # Make reservation old
    session = repository.get_session()
    try:
        reservation = session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
        session.commit()
    finally:
        session.close()

    from fastapi import HTTPException
    try:
        service.confirm_reservation(reservation_id)
    except HTTPException:
        pass

    # Stock should be restored
    stock = repository.get_sku_stock("SKU-010")
    assert stock == 100


def test_cancel_reservation(service):
    """Test cancelling a reservation."""
    service.create_sku("SKU-011", 100)
    res = service.create_reservation("SKU-011", 30, "key-008")
    reservation_id = res["id"]

    result = service.cancel_reservation(reservation_id)
    assert result["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(service):
    """Test that cancelling reservation restores stock."""
    service.create_sku("SKU-012", 100)
    res = service.create_reservation("SKU-012", 35, "key-009")
    reservation_id = res["id"]
    stock_after_res = service.repo.get_sku_stock("SKU-012")
    assert stock_after_res == 65  # 100 - 35

    service.cancel_reservation(reservation_id)
    stock_after_cancel = service.repo.get_sku_stock("SKU-012")
    assert stock_after_cancel == 100


def test_cancel_non_pending_reservation(service):
    """Test that cancelling non-PENDING reservation fails."""
    service.create_sku("SKU-013", 100)
    res = service.create_reservation("SKU-013", 20, "key-010")
    reservation_id = res["id"]

    service.confirm_reservation(reservation_id)  # Confirm first

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(reservation_id)  # Cancel should fail
    assert exc_info.value.status_code == 400


def test_get_orders(service):
    """Test retrieving orders."""
    service.create_sku("SKU-014", 200)

    # Create and confirm multiple reservations
    for i in range(12):
        res = service.create_reservation("SKU-014", 10, f"key-{i}")
        service.confirm_reservation(res["id"])

    orders_data = service.get_orders(page=1, size=10)
    assert orders_data["page"] == 1
    assert orders_data["size"] == 10
    assert len(orders_data["orders"]) == 10
    assert orders_data["total"] == 12


def test_get_orders_second_page(service):
    """Test pagination of orders."""
    service.create_sku("SKU-015", 300)

    # Create and confirm 15 reservations
    for i in range(15):
        res = service.create_reservation("SKU-015", 10, f"key-page-{i}")
        service.confirm_reservation(res["id"])

    page2 = service.get_orders(page=2, size=10)
    assert page2["page"] == 2
    assert len(page2["orders"]) == 5
    assert page2["total"] == 15
