import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


class TestDBState:
    """State holder for test database."""
    session_factory = None


@pytest.fixture
def client():
    """Create a test client with temporary file-based database."""
    db_fd, db_path = tempfile.mkstemp()
    db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestDBState.session_factory = sessionmaker(bind=engine)

    def override_get_db():
        db = TestDBState.session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    TestDBState.session_factory = None

    os.close(db_fd)
    os.unlink(db_path)


def test_health(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    """Test creating a SKU."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["initial_stock"] == 100
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    """Test that missing API key returns 401."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert "Missing API key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client):
    """Test that invalid API key returns 401."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]


def test_create_sku_duplicate(client):
    """Test that duplicate SKUs return 400."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_adjust_stock_success(client):
    """Test adjusting stock."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_nonexistent_sku(client):
    """Test adjusting stock for non-existent SKU."""
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 50},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_create_reservation_success(client):
    """Test creating a reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key-1"


def test_create_reservation_insufficient_stock(client):
    """Test that insufficient stock returns 400."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 30},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_idempotent_reservation(client):
    """Test idempotency key prevents duplicate reservations."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    first = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert first.status_code == 201
    first_data = first.json()

    second = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert second.status_code == 201
    second_data = second.json()

    assert first_data["id"] == second_data["id"]
    assert first_data["created_at"] == second_data["created_at"]

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert sku_response.json()["available_stock"] == 50


def test_confirm_reservation_success(client):
    """Test confirming a reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id


def test_confirm_expired_reservation(client):
    """Test that expired reservations cannot be confirmed."""
    from src.commerce_service.models import ReservationModel
    from datetime import datetime, timedelta
    from sqlalchemy import select

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    db = TestDBState.session_factory()
    try:
        reservation = db.scalar(select(ReservationModel).where(ReservationModel.id == reservation_id))
        if reservation:
            reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
            db.commit()
    finally:
        db.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_cancel_reservation_success(client):
    """Test canceling a reservation restores stock."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert sku_response.json()["available_stock"] == 100


def test_cancel_non_pending_reservation(client):
    """Test that confirmed reservations cannot be cancelled."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 400
    assert "cannot be cancelled" in response.json()["detail"]


def test_get_orders_paginated(client):
    """Test paginated order retrieval."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": "test-key-12345"},
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "test-key-12345"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key-12345"},
        )

    response = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert len(data["orders"]) == 10
    assert data["total"] == 15

    response = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["total"] == 15


def test_get_orders_default_pagination(client):
    """Test default pagination values."""
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": "test-key-12345"},
    )

    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "test-key-12345"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key-12345"},
        )

    response = client.get(
        "/orders",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert len(data["orders"]) == 5
    assert data["total"] == 5
