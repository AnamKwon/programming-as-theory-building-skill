"""Tests for the API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app
from commerce_service.repository import Base, get_db
from commerce_service.security import VALID_API_KEY


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
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
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "SKU-001"
    assert data["name"] == "Test Product"
    assert data["stock"] == 0
    assert data["reserved"] == 0
    assert data["available"] == 0


def test_create_sku_without_api_key(client):
    """Test that SKU creation requires API key."""
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"}
    )
    assert response.status_code == 403


def test_create_sku_with_invalid_api_key(client):
    """Test that invalid API key is rejected."""
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 403


def test_get_sku(client):
    """Test getting SKU details."""
    # Create SKU first
    create_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = create_response.json()["id"]

    # Get SKU
    response = client.get(f"/skus/{sku_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sku_id
    assert data["code"] == "SKU-001"


def test_get_nonexistent_sku(client):
    """Test getting a nonexistent SKU returns 404."""
    response = client.get("/skus/999")
    assert response.status_code == 404


def test_adjust_stock(client):
    """Test stock adjustment."""
    # Create SKU
    create_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = create_response.json()["id"]

    # Adjust stock
    response = client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 100


def test_adjust_stock_without_api_key(client):
    """Test that stock adjustment requires API key."""
    response = client.post(
        "/skus/1/adjust-stock",
        json={"adjustment": 100}
    )
    assert response.status_code == 403


def test_create_reservation_success(client):
    """Test successful reservation creation."""
    # Create and stock SKU
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    """Test reservation fails with insufficient stock."""
    # Create SKU with limited stock
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 30},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    """Test that duplicate idempotency keys return same reservation."""
    # Create and stock SKU
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Create first reservation
    res1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    res1_id = res1.json()["id"]

    # Create second with same key
    res2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    res2_id = res2.json()["id"]

    assert res1_id == res2_id


def test_confirm_reservation_success(client):
    """Test successful reservation confirmation."""
    # Create and stock SKU
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert data["status"] == "pending"


def test_confirm_reservation_without_api_key(client):
    """Test that confirmation requires API key."""
    response = client.post("/reservations/1/confirm")
    assert response.status_code == 403


def test_cancel_reservation_success(client):
    """Test successful reservation cancellation."""
    # Create and stock SKU
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_get_order(client):
    """Test getting an order."""
    # Setup: create SKU, reserve, confirm
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "key-001"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    order_id = order_response.json()["id"]

    # Get order
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id


def test_list_orders_pagination(client):
    """Test order listing with pagination."""
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Test Product"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 500},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Create and confirm multiple reservations
    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"key-{i:03d}"
            },
            headers={"X-API-Key": VALID_API_KEY}
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY}
        )

    # Test pagination
    response = client.get("/orders?offset=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["offset"] == 0
    assert data["limit"] == 2

    response = client.get("/orders?offset=2&limit=2")
    data = response.json()
    assert len(data["items"]) == 2

    response = client.get("/orders?offset=4&limit=2")
    data = response.json()
    assert len(data["items"]) == 1


def test_list_orders_default_pagination(client):
    """Test order listing with default pagination parameters."""
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["offset"] == 0
    assert data["limit"] == 20
    assert data["total"] == 0
    assert data["items"] == []
