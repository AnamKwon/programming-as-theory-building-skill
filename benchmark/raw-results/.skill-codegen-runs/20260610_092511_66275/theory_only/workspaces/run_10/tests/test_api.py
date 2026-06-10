"""Integration tests for API endpoints."""

import os
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.commerce_service.app import app
from src.commerce_service.models import Base
from src.commerce_service.repository import SessionLocal

# Override database for testing
@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from src.commerce_service import repository

    original_get_db = repository.get_db
    app.dependency_overrides[original_get_db] = override_get_db
    yield
    del app.dependency_overrides[original_get_db]


@pytest.fixture
def client(test_db):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def api_key():
    """Get test API key."""
    return "dev-key-change-in-production"


def test_health(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_requires_api_key(client):
    """Test that SKU creation requires API key."""
    response = client.post("/skus", json={"id": "PROD-001", "name": "Test"})
    assert response.status_code == 403


def test_create_sku_success(client, api_key):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "PROD-001"
    assert data["name"] == "Test Product"
    assert "created_at" in data


def test_create_sku_duplicate_fails(client, api_key):
    """Test that duplicate SKU creation fails."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Another Product"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409


def test_get_sku(client, api_key):
    """Test getting SKU details."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    response = client.get("/skus/PROD-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "PROD-001"


def test_get_sku_not_found(client):
    """Test getting non-existent SKU."""
    response = client.get("/skus/NONEXISTENT")
    assert response.status_code == 404


def test_adjust_stock(client, api_key):
    """Test stock adjustment."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_quantity"] == 100
    assert data["reserved_quantity"] == 0


def test_get_inventory(client, api_key):
    """Test getting inventory state."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.get("/inventory/PROD-001")
    assert response.status_code == 200
    data = response.json()
    assert data["available_quantity"] == 100


def test_create_reservation_success(client, api_key):
    """Test successful reservation creation."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "PROD-001"
    assert data["quantity"] == 50
    assert data["status"] == "pending"
    assert "id" in data
    assert "expires_at" in data


def test_create_reservation_insufficient_stock(client, api_key):
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 10},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_reservation_idempotency(client, api_key):
    """Test idempotent reservation creation."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 200},
        headers={"X-API-Key": api_key},
    )

    idempotency_key = str(uuid.uuid4())
    res1 = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
            "idempotency_key": idempotency_key,
        },
        headers={"X-API-Key": api_key},
    )
    res1_id = res1.json()["id"]

    # Same idempotency key should return same reservation
    res2 = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-002",
            "quantity": 60,
            "idempotency_key": idempotency_key,
        },
        headers={"X-API-Key": api_key},
    )
    assert res2.json()["id"] == res1_id

    # Verify only one reservation was created (inventory should have only 50 reserved)
    inventory = client.get("/inventory/PROD-001").json()
    assert inventory["reserved_quantity"] == 50


def test_confirm_reservation(client, api_key):
    """Test confirming a reservation."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
        },
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"


def test_cancel_reservation(client, api_key):
    """Test cancelling a reservation."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
        },
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"

    # Verify inventory is released
    inventory = client.get("/inventory/PROD-001").json()
    assert inventory["available_quantity"] == 100
    assert inventory["reserved_quantity"] == 0


def test_get_order(client, api_key):
    """Test getting order details."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
        headers={"X-API-Key": api_key},
    )

    client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
        },
        headers={"X-API-Key": api_key},
    )

    response = client.get("/orders/ORDER-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "ORDER-001"
    assert data["status"] == "pending"
    assert len(data["reservations"]) == 1


def test_list_orders_pagination(client, api_key):
    """Test order listing with pagination."""
    client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 1000},
        headers={"X-API-Key": api_key},
    )

    # Create 25 orders
    for i in range(25):
        client.post(
            "/reservations",
            json={
                "sku_id": "PROD-001",
                "order_id": f"ORDER-{i:03d}",
                "quantity": 10,
            },
            headers={"X-API-Key": api_key},
        )

    # Test first page
    response = client.get("/orders?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["has_more"] is True

    # Test second page
    response = client.get("/orders?page=2&page_size=10")
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["has_more"] is True

    # Test last page
    response = client.get("/orders?page=3&page_size=10")
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["has_more"] is False


def test_unauthorized_mutation_without_api_key(client):
    """Test that mutations without API key are rejected."""
    response = client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
    )
    assert response.status_code == 403

    response = client.post(
        "/inventory/PROD-001/adjust",
        json={"quantity_change": 100},
    )
    assert response.status_code == 403

    response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "order_id": "ORDER-001",
            "quantity": 50,
        },
    )
    assert response.status_code == 403


def test_unauthorized_mutation_with_wrong_api_key(client):
    """Test that mutations with wrong API key are rejected."""
    response = client.post(
        "/skus",
        json={"id": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
