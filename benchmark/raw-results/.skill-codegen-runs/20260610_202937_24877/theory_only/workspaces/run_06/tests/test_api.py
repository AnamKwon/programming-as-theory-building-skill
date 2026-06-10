"""Tests for the API endpoints."""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from src.commerce_service.app import app
from src.commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client(temp_db):
    """Create a test client with a temporary database."""
    # Patch the get_repository dependency
    from src.commerce_service import app as app_module

    def get_test_repo():
        return Repository(db_file=temp_db)

    app.dependency_overrides[app_module.get_repository] = get_test_repo
    yield TestClient(app)
    app.dependency_overrides.clear()


VALID_API_KEY = "test-api-key-12345"
INVALID_API_KEY = "invalid-key"

HEADERS_VALID = {"X-API-Key": VALID_API_KEY}
HEADERS_INVALID = {"X-API-Key": INVALID_API_KEY}


def test_health_no_auth(client):
    """Test health endpoint requires no authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    """Test creating a SKU with valid API key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-001", "initial_stock": 100},
        headers=HEADERS_VALID
    )
    assert response.status_code == 201
    assert response.json() == {"sku": "TEST-SKU-001", "available_stock": 100}


def test_create_sku_unauthorized(client):
    """Test creating a SKU without API key fails."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-002", "initial_stock": 50}
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    """Test creating a SKU with invalid API key fails."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-003", "initial_stock": 75},
        headers=HEADERS_INVALID
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    """Test adjusting stock levels."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-004", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-004", "amount": 25},
        headers=HEADERS_VALID
    )
    assert response.status_code == 200
    assert response.json() == {"sku": "TEST-SKU-004", "available_stock": 125}


def test_adjust_stock_unauthorized(client):
    """Test adjusting stock without authentication fails."""
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-005", "amount": -10}
    )
    assert response.status_code == 403


def test_create_reservation_success(client):
    """Test creating a reservation with sufficient stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-006", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-006",
            "quantity": 30,
            "idempotency_key": "unique-key-1"
        },
        headers=HEADERS_VALID
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-006"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    """Test reservation fails with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-007", "initial_stock": 50},
        headers=HEADERS_VALID
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-007",
            "quantity": 100,
            "idempotency_key": "unique-key-2"
        },
        headers=HEADERS_VALID
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient stock"}


def test_reservation_idempotency(client):
    """Test idempotent reservation requests."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-008", "initial_stock": 200},
        headers=HEADERS_VALID
    )

    # First request
    response1 = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-008",
            "quantity": 50,
            "idempotency_key": "unique-key-3"
        },
        headers=HEADERS_VALID
    )
    assert response1.status_code == 201
    data1 = response1.json()
    reservation_id = data1["id"]

    # Second request with same idempotency key
    response2 = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-008",
            "quantity": 50,
            "idempotency_key": "unique-key-3"
        },
        headers=HEADERS_VALID
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data1 == data2
    assert data2["id"] == reservation_id


def test_confirm_reservation_success(client):
    """Test confirming a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-009", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-009",
            "quantity": 40,
            "idempotency_key": "unique-key-4"
        },
        headers=HEADERS_VALID
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS_VALID
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client, temp_db):
    """Test confirming an expired reservation fails."""
    from datetime import datetime, timezone, timedelta

    client.post(
        "/skus",
        json={"sku": "TEST-SKU-010", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-010",
            "quantity": 25,
            "idempotency_key": "unique-key-5"
        },
        headers=HEADERS_VALID
    )
    reservation_id = res_response.json()["id"]

    # Manually set the reservation's created_at to > 300 seconds ago
    repo = Repository(db_file=temp_db)
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    conn = repo.get_connection()
    conn.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id)
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS_VALID
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Reservation expired"}


def test_cancel_reservation_success(client):
    """Test canceling a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-011", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-011",
            "quantity": 30,
            "idempotency_key": "unique-key-6"
        },
        headers=HEADERS_VALID
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=HEADERS_VALID
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders_pagination(client):
    """Test paginated orders listing."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-012", "initial_stock": 1000},
        headers=HEADERS_VALID
    )

    # Create and confirm multiple reservations
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "TEST-SKU-012",
                "quantity": 10,
                "idempotency_key": f"pagination-key-{i}"
            },
            headers=HEADERS_VALID
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=HEADERS_VALID
        )

    # Get first page
    response1 = client.get(
        "/orders?page=1&size=10",
        headers=HEADERS_VALID
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["page"] == 1
    assert data1["size"] == 10
    assert data1["total"] == 25
    assert len(data1["orders"]) == 10

    # Get second page
    response2 = client.get(
        "/orders?page=2&size=10",
        headers=HEADERS_VALID
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 10

    # Get third page
    response3 = client.get(
        "/orders?page=3&size=10",
        headers=HEADERS_VALID
    )
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["orders"]) == 5


def test_get_orders_unauthorized(client):
    """Test getting orders without authentication fails."""
    response = client.get("/orders")
    assert response.status_code == 403


def test_confirm_non_pending_reservation(client):
    """Test confirming a non-PENDING reservation fails."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-013", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-013",
            "quantity": 20,
            "idempotency_key": "unique-key-7"
        },
        headers=HEADERS_VALID
    )
    reservation_id = res_response.json()["id"]

    # Confirm once
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS_VALID
    )

    # Try to confirm again
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS_VALID
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Reservation is not in PENDING status"}


def test_cancel_non_pending_reservation(client):
    """Test canceling a non-PENDING reservation fails."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-014", "initial_stock": 100},
        headers=HEADERS_VALID
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-014",
            "quantity": 20,
            "idempotency_key": "unique-key-8"
        },
        headers=HEADERS_VALID
    )
    reservation_id = res_response.json()["id"]

    # Confirm the reservation
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS_VALID
    )

    # Try to cancel
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=HEADERS_VALID
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Reservation is not in PENDING status"}
