"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db_session():
    """Create in-memory SQLite session for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """Create test client with overridden database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_health_check(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_create_sku_success(client):
    """Test successful SKU creation."""
    headers = {"X-API-Key": "test-key-12345"}
    response = client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Test Product"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "sku_test_1"
    assert data["name"] == "Test Product"
    assert data["available_quantity"] == 0


def test_create_sku_unauthorized(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Test Product"},
    )
    assert response.status_code == 401


def test_create_sku_invalid_key(client):
    """Test SKU creation with invalid API key."""
    headers = {"X-API-Key": "invalid-key"}
    response = client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Test Product"},
        headers=headers,
    )
    assert response.status_code == 403


def test_get_sku(client):
    """Test SKU retrieval."""
    headers = {"X-API-Key": "test-key-12345"}

    # Create SKU
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )

    # Retrieve SKU
    response = client.get("/skus/sku_test_1")
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "sku_test_1"


def test_get_sku_not_found(client):
    """Test SKU retrieval for nonexistent SKU."""
    response = client.get("/skus/nonexistent")
    assert response.status_code == 404


def test_adjust_stock(client):
    """Test stock adjustment."""
    headers = {"X-API-Key": "test-key-12345"}

    # Create SKU
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )

    # Adjust stock up
    response = client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 100, "idempotency_key": "adj_1"},
        headers=headers,
    )
    assert response.status_code == 204

    # Verify
    sku_response = client.get("/skus/sku_test_1")
    assert sku_response.json()["available_quantity"] == 100


def test_adjust_stock_unauthorized(client):
    """Test stock adjustment without API key."""
    response = client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 100, "idempotency_key": "adj_1"},
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    """Test successful reservation creation."""
    headers = {"X-API-Key": "test-key-12345"}

    # Create SKU and add stock
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 100, "idempotency_key": "adj_1"},
        headers=headers,
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku_id": "sku_test_1",
            "quantity": 50,
            "idempotency_key": "res_key_1",
            "ttl_seconds": 1800,
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "sku_test_1"
    assert data["quantity"] == 50
    assert data["status"] == "pending"
    assert "reservation_id" in data


def test_create_reservation_insufficient_stock(client):
    """Test reservation creation fails with insufficient stock."""
    headers = {"X-API-Key": "test-key-12345"}

    # Create SKU with limited stock
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 30, "idempotency_key": "adj_1"},
        headers=headers,
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku_id": "sku_test_1",
            "quantity": 50,
            "idempotency_key": "res_key_1",
        },
        headers=headers,
    )
    assert response.status_code == 409


def test_create_reservation_idempotency(client):
    """Test idempotent reservation creation."""
    headers = {"X-API-Key": "test-key-12345"}

    # Create SKU and add stock
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 100, "idempotency_key": "adj_1"},
        headers=headers,
    )

    # Create first reservation
    res_1 = client.post(
        "/reservations",
        json={
            "sku_id": "sku_test_1",
            "quantity": 50,
            "idempotency_key": "unique_key_1",
        },
        headers=headers,
    )
    res_id_1 = res_1.json()["reservation_id"]

    # Retry with same idempotency key
    res_2 = client.post(
        "/reservations",
        json={
            "sku_id": "sku_test_1",
            "quantity": 50,
            "idempotency_key": "unique_key_1",
        },
        headers=headers,
    )
    res_id_2 = res_2.json()["reservation_id"]

    # Should return same reservation
    assert res_id_1 == res_id_2

    # Verify only one reservation in database
    sku = client.get("/skus/sku_test_1").json()
    assert sku["reserved_quantity"] == 50


def test_confirm_reservation_success(client):
    """Test successful reservation confirmation."""
    headers = {"X-API-Key": "test-key-12345"}

    # Setup: create SKU, add stock, create reservation
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 100, "idempotency_key": "adj_1"},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": "sku_test_1",
            "quantity": 50,
            "idempotency_key": "res_key_1",
        },
        headers=headers,
    )
    res_id = res_response.json()["reservation_id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "sku_test_1"
    assert data["quantity"] == 50
    assert data["status"] == "pending"  # Order status is initially pending
    assert "order_id" in data


def test_cancel_reservation_success(client):
    """Test successful reservation cancellation."""
    headers = {"X-API-Key": "test-key-12345"}

    # Setup
    client.post(
        "/skus",
        json={"sku_id": "sku_test_1", "name": "Product"},
        headers=headers,
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "sku_test_1", "delta": 100, "idempotency_key": "adj_1"},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": "sku_test_1",
            "quantity": 50,
            "idempotency_key": "res_key_1",
        },
        headers=headers,
    )
    res_id = res_response.json()["reservation_id"]

    # Cancel
    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 204

    # Verify stock released
    sku = client.get("/skus/sku_test_1").json()
    assert sku["reserved_quantity"] == 0
    assert sku["available_quantity"] == 100


def test_cancel_reservation_unauthorized(client):
    """Test cancellation without API key."""
    response = client.post("/reservations/res_123/cancel")
    assert response.status_code == 401


def test_list_orders_empty(client):
    """Test orders list when empty."""
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["orders"] == []
    assert data["total"] == 0
    assert data["limit"] == 20
    assert data["offset"] == 0


def test_list_orders_with_pagination(client):
    """Test orders pagination."""
    headers = {"X-API-Key": "test-key-12345"}

    # Create multiple orders
    for i in range(5):
        client.post(
            "/skus",
            json={"sku_id": f"sku_{i}", "name": f"Product {i}"},
            headers=headers,
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": f"sku_{i}", "delta": 100, "idempotency_key": f"adj_{i}"},
            headers=headers,
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": f"sku_{i}",
                "quantity": 10,
                "idempotency_key": f"res_key_{i}",
            },
            headers=headers,
        )
        res_id = res.json()["reservation_id"]
        client.post(f"/reservations/{res_id}/confirm", headers=headers)

    # Test pagination
    response = client.get("/orders?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0

    # Second page
    response = client.get("/orders?limit=2&offset=2")
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["offset"] == 2

    # Last page
    response = client.get("/orders?limit=2&offset=4")
    data = response.json()
    assert len(data["orders"]) == 1
