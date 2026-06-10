"""Tests for the API endpoints."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base
from src.commerce_service.app import app, get_db


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    """Create a test client with test database."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client):
    """Test SKU creation with valid API key."""
    response = client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "SKU-001"
    assert data["name"] == "Test Product"


def test_create_sku_unauthorized(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
    )
    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]


def test_create_sku_invalid_key(client):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client):
    """Test stock adjustment."""
    # Create SKU first
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )

    # Adjust stock
    response = client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 100


def test_adjust_stock_nonexistent_sku(client):
    """Test adjusting stock for nonexistent SKU."""
    response = client.post(
        "/api/stock/adjust",
        json={"sku_id": "NONEXISTENT", "delta": 10},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    """Test reservation creation with sufficient stock."""
    # Setup: Create SKU and stock
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": "test-key"},
    )

    # Create reservation
    response = client.post(
        "/api/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-key-1",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["status"] == "reserved"
    assert data["id"] is not None


def test_create_reservation_insufficient_stock(client):
    """Test reservation fails with insufficient stock."""
    # Setup: Create SKU with limited stock
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 5},
        headers={"X-API-Key": "test-key"},
    )

    # Try to reserve more than available
    response = client.post(
        "/api/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-key-1",
        },
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_confirm_reservation(client):
    """Test confirming a reservation."""
    # Setup
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": "test-key"},
    )

    res = client.post(
        "/api/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-key-1",
        },
        headers={"X-API-Key": "test-key"},
    )
    reservation_id = res.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/api/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "confirm-idempotency-key-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"


def test_confirm_nonexistent_reservation(client):
    """Test confirming a nonexistent reservation."""
    response = client.post(
        "/api/reservations/nonexistent-id/confirm",
        json={"idempotency_key": "confirm-idempotency-key-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 404


def test_cancel_reservation(client):
    """Test cancelling a reservation."""
    # Setup
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": "test-key"},
    )

    res = client.post(
        "/api/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-key-1",
        },
        headers={"X-API-Key": "test-key"},
    )
    reservation_id = res.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/api/reservations/{reservation_id}/cancel",
        json={"idempotency_key": "cancel-idempotency-key-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_list_orders_pagination(client):
    """Test listing orders with pagination."""
    # Setup: Create SKU and stock
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 1000},
        headers={"X-API-Key": "test-key"},
    )

    # Create multiple reservations
    for i in range(15):
        client.post(
            "/api/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 10,
                "idempotency_key": f"idempotency-key-{i}",
            },
            headers={"X-API-Key": "test-key"},
        )

    # Test default pagination
    response = client.get("/api/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10
    assert data["skip"] == 0
    assert data["limit"] == 10

    # Test custom pagination
    response = client.get("/api/orders?skip=10&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_list_orders_invalid_pagination(client):
    """Test listing orders with invalid pagination parameters."""
    response = client.get("/api/orders?skip=-1&limit=10")
    assert response.status_code == 400

    response = client.get("/api/orders?skip=0&limit=0")
    assert response.status_code == 400


def test_reservation_idempotent_retry(client):
    """Test that retrying with same idempotency key returns same result."""
    # Setup
    client.post(
        "/api/skus",
        json={"id": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": "test-key"},
    )

    # Create reservation twice with same idempotency key
    response1 = client.post(
        "/api/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 10,
            "idempotency_key": "unique-key-1",
        },
        headers={"X-API-Key": "test-key"},
    )
    response2 = client.post(
        "/api/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 10,
            "idempotency_key": "unique-key-1",
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    # Both should return a reservation (idempotency expected)
    assert response1.json()["id"] is not None
    assert response2.json()["id"] is not None
