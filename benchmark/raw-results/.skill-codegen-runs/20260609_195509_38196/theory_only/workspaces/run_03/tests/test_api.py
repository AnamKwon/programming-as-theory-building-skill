"""Tests for the FastAPI application and HTTP endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import Service


@pytest.fixture(autouse=True)
def setup_test_db():
    """Replace repository with in-memory database for tests."""
    from src.commerce_service import app as app_module

    old_repo = app_module.repo
    old_service = app_module.service

    app_module.repo = Repository("sqlite:///:memory:")
    app_module.service = Service(app_module.repo)

    yield

    app_module.repo = old_repo
    app_module.service = old_service


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_unauthorized(client):
    """Test creating SKU without API key."""
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
    )
    assert response.status_code == 401


def test_create_sku_invalid_key(client):
    """Test creating SKU with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_create_sku_authorized(client):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["name"] == "Blue Widget"


def test_adjust_stock(client):
    """Test stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available"] == 100


def test_reserve_success(client):
    """Test successful reservation."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "pending"
    assert data["quantity"] == 5


def test_reserve_insufficient_stock(client):
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 3},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_reserve_idempotent_retry(client):
    """Test idempotent reservation retry."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key"},
    )

    client.post(
        "/reservations",
        json={"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 400
    assert "already used" in response.json()["detail"]


def test_confirm_reservation(client):
    """Test confirming a reservation."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "confirmed"
    assert data["order_id"] is not None


def test_cancel_reservation(client):
    """Test canceling a reservation."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "cancelled"


def test_list_orders_unauthorized(client):
    """Test listing orders without API key."""
    response = client.get("/orders")
    assert response.status_code == 401


def test_list_orders_empty(client):
    """Test listing orders when empty."""
    response = client.get("/orders", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["orders"] == []
    assert data["has_next"] is False


def test_list_orders_with_pagination(client):
    """Test order listing with pagination."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Blue Widget"},
        headers={"X-API-Key": "test-key"},
    )
    client.post(
        "/skus/WIDGET-001/stock",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key"},
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "WIDGET-001", "quantity": 1, "idempotency_key": f"order-{i}"},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )

    response = client.get(
        "/orders?page=1&page_size=10",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 15
    assert data["has_next"] is True
    assert data["page"] == 1

    response = client.get(
        "/orders?page=2&page_size=10",
        headers={"X-API-Key": "test-key"},
    )
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["has_next"] is False
