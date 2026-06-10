"""API endpoint tests."""
import pytest
import time
from fastapi.testclient import TestClient
from src.commerce_service.app import app, db, service
from src.commerce_service.security import API_TOKEN


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    db.db_path = ":memory:"
    db.init_db()
    yield


def get_headers():
    """Get headers with API token."""
    return {"X-API-Token": API_TOKEN}


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client):
    """Test SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_headers()
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU-001"
    assert response.json()["initial_stock"] == 100


def test_create_sku_unauthorized(client):
    """Test SKU creation without token."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100}
    )
    assert response.status_code == 401
    assert "Missing API token" in response.json()["detail"]


def test_create_sku_invalid_token(client):
    """Test SKU creation with invalid token."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": "wrong-token"}
    )
    assert response.status_code == 401
    assert "Invalid API token" in response.json()["detail"]


def test_adjust_stock(client):
    """Test stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "SKU-002", "initial_stock": 50},
        headers=get_headers()
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-002", "amount": 25},
        headers=get_headers()
    )
    assert response.status_code == 200
    assert response.json()["new_stock"] == 75


def test_adjust_stock_unauthorized(client):
    """Test stock adjustment without token."""
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-002", "amount": 25}
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    """Test happy path: reservation creation."""
    client.post(
        "/skus",
        json={"sku": "SKU-003", "initial_stock": 100},
        headers=get_headers()
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-003", "quantity": 30, "idempotency_key": "key-1"},
        headers=get_headers()
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU-003"
    assert response.json()["quantity"] == 30
    assert response.json()["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "SKU-004", "initial_stock": 20},
        headers=get_headers()
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-004", "quantity": 50, "idempotency_key": "key-2"},
        headers=get_headers()
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    """Test idempotent reservation creation."""
    client.post(
        "/skus",
        json={"sku": "SKU-005", "initial_stock": 100},
        headers=get_headers()
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-005", "quantity": 25, "idempotency_key": "key-3"},
        headers=get_headers()
    )
    assert response1.status_code == 201
    reservation_id = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-005", "quantity": 25, "idempotency_key": "key-3"},
        headers=get_headers()
    )
    assert response2.status_code == 200
    assert response2.json()["id"] == reservation_id


def test_create_reservation_unauthorized(client):
    """Test reservation creation without token."""
    response = client.post(
        "/reservations",
        json={"sku": "SKU-003", "quantity": 30, "idempotency_key": "key-1"}
    )
    assert response.status_code == 401


def test_confirm_reservation_success(client):
    """Test happy path: confirm reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-006", "initial_stock": 100},
        headers=get_headers()
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-006", "quantity": 40, "idempotency_key": "key-4"},
        headers=get_headers()
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers()
    )
    assert response.status_code == 200
    assert response.json()["sku"] == "SKU-006"
    assert response.json()["quantity"] == 40


def test_confirm_reservation_not_pending(client):
    """Test confirming a non-PENDING reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-007", "initial_stock": 100},
        headers=get_headers()
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-007", "quantity": 20, "idempotency_key": "key-5"},
        headers=get_headers()
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers()
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers()
    )
    assert response.status_code == 400
    assert "not in PENDING status" in response.json()["detail"]


def test_confirm_reservation_expired(client):
    """Test confirming an expired reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-008", "initial_stock": 100},
        headers=get_headers()
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-008", "quantity": 35, "idempotency_key": "key-6"},
        headers=get_headers()
    )
    reservation_id = res.json()["id"]

    time.sleep(301)

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers()
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_confirm_reservation_unauthorized(client):
    """Test confirm without token."""
    response = client.post(
        "/reservations/1/confirm"
    )
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    """Test reservation cancellation."""
    client.post(
        "/skus",
        json={"sku": "SKU-009", "initial_stock": 100},
        headers=get_headers()
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-009", "quantity": 50, "idempotency_key": "key-7"},
        headers=get_headers()
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_headers()
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_not_pending(client):
    """Test cancelling a non-PENDING reservation."""
    client.post(
        "/skus",
        json={"sku": "SKU-010", "initial_stock": 100},
        headers=get_headers()
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-010", "quantity": 25, "idempotency_key": "key-8"},
        headers=get_headers()
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers()
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_headers()
    )
    assert response.status_code == 400
    assert "not in PENDING status" in response.json()["detail"]


def test_cancel_reservation_unauthorized(client):
    """Test cancel without token."""
    response = client.post(
        "/reservations/1/cancel"
    )
    assert response.status_code == 401


def test_get_orders_empty(client):
    """Test getting orders when none exist."""
    response = client.get("/orders")
    assert response.status_code == 200
    assert response.json()["orders"] == []
    assert response.json()["total"] == 0


def test_get_orders_pagination(client):
    """Test orders pagination."""
    client.post(
        "/skus",
        json={"sku": "SKU-011", "initial_stock": 1000},
        headers=get_headers()
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU-011", "quantity": 10, "idempotency_key": f"key-p{i}"},
            headers=get_headers()
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_headers()
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    assert len(response.json()["orders"]) == 10
    assert response.json()["total"] == 25
    assert response.json()["page"] == 1

    response = client.get("/orders?page=2&size=10")
    assert len(response.json()["orders"]) == 10

    response = client.get("/orders?page=3&size=10")
    assert len(response.json()["orders"]) == 5


def test_get_orders_no_auth_required(client):
    """Test that GET /orders doesn't require authentication."""
    response = client.get("/orders")
    assert response.status_code == 200
