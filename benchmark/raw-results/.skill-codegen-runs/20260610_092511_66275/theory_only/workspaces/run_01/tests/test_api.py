"""Tests for the HTTP API endpoints."""
import pytest
from fastapi.testclient import TestClient
import tempfile
import os

from commerce_service.app import app, db, service
from commerce_service.repository import Database


@pytest.fixture(autouse=True)
def setup_temp_db():
    """Use a temporary database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    test_db = Database(f"sqlite:///{path}")

    # Monkey-patch the global db and service
    from commerce_service import app as app_module
    original_db = app_module.db
    original_service = app_module.service
    app_module.db = test_db
    app_module.service = test_db.__class__.__init__.__globals__["CommerceService"](test_db)

    yield test_db

    # Restore originals
    app_module.db = original_db
    app_module.service = original_service

    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def api_key():
    """Return a valid API key for testing."""
    return "test-key-1"


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client, api_key):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "SKU-001"
    assert data["name"] == "Widget"


def test_create_sku_unauthorized(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
    )
    assert response.status_code == 401
    assert "Invalid or missing API key" in response.json()["detail"]


def test_create_sku_invalid_key(client):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client, api_key):
    """Test successful stock adjustment."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 100
    assert data["available"] == 100


def test_adjust_stock_not_found(client, api_key):
    """Test stock adjustment for non-existent SKU."""
    response = client.post(
        "/stock/adjust",
        json={"sku_id": "NONEXISTENT", "delta": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_create_reservation_success(client, api_key):
    """Test successful reservation creation."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client, api_key):
    """Test reservation fails with insufficient stock."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 30},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 400


def test_create_reservation_idempotent(client, api_key):
    """Test idempotent reservation creation."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": api_key},
    )

    # First reservation
    res1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": api_key},
    )
    assert res1.status_code == 201
    res1_id = res1.json()["id"]

    # Retry with same idempotency key
    res2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": api_key},
    )
    assert res2.status_code == 201
    assert res2.json()["id"] == res1_id


def test_confirm_reservation_success(client, api_key):
    """Test successful reservation confirmation."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"]
    assert data["quantity"] == 50


def test_confirm_reservation_not_found(client, api_key):
    """Test confirming non-existent reservation."""
    response = client.post(
        "/reservations/NONEXISTENT/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 400


def test_cancel_reservation_success(client, api_key):
    """Test successful reservation cancellation."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_order_success(client, api_key):
    """Test successful order lookup."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    order_id = confirm_res.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["status"] == "confirmed"


def test_get_order_not_found(client):
    """Test order lookup for non-existent order."""
    response = client.get("/orders/NONEXISTENT")
    assert response.status_code == 404


def test_list_orders_pagination(client, api_key):
    """Test order listing with pagination."""
    client.post(
        "/skus",
        json={"id": "SKU-001", "name": "Widget"},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU-001", "delta": 1000},
        headers={"X-API-Key": api_key},
    )

    # Create 5 orders
    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": api_key},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    # Test first page
    response = client.get("/orders?offset=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["offset"] == 0
    assert data["limit"] == 2

    # Test second page
    response = client.get("/orders?offset=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2

    # Test beyond available items
    response = client.get("/orders?offset=10&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 0
