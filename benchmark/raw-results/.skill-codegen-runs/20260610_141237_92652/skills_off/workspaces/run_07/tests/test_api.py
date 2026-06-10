"""Tests for the API endpoints."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import os

from commerce_service.app import app
from commerce_service.repository import Repository


@pytest.fixture(autouse=True)
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = str(Path(temp_dir) / "test.db")

    # Override the module-level repo
    from commerce_service import app as app_module

    original_repo = app_module.repo
    app_module.repo = Repository(db_path)
    app_module.service = app_module.Service(app_module.repo)

    yield db_path

    # Restore original
    app_module.repo = original_repo

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def api_key():
    """Get the test API key."""
    os.environ["API_KEY"] = "test-secret-key"
    return "test-secret-key"


def get_auth_header(api_key: str) -> dict:
    """Get authorization header."""
    return {"Authorization": f"Bearer {api_key}"}


def test_health_check(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, api_key):
    """Test SKU creation endpoint."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_unauthorized(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_key(client):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header("wrong-key"),
    )
    assert response.status_code == 401


def test_adjust_stock(client, api_key):
    """Test stock adjustment endpoint."""
    # Create SKU first
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )

    # Adjust stock
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_stock"] == 150


def test_create_reservation_success(client, api_key):
    """Test successful reservation creation."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key-1"


def test_create_reservation_insufficient_stock(client, api_key):
    """Test reservation with insufficient stock."""
    # Create SKU with low stock
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 30},
        headers=get_auth_header(api_key),
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_reservation_idempotency(client, api_key):
    """Test reservation idempotency with same key."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )

    # Create first reservation
    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    assert response1.status_code == 201
    reservation_id = response1.json()["id"]

    # Create second reservation with same key
    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    assert response2.status_code == 201
    assert response2.json()["id"] == reservation_id

    # Verify stock is 50 (not 0)
    sku_resp = client.post(
        "/skus",
        json={"sku": "SKU-002", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    assert sku_resp.status_code == 201


def test_confirm_reservation(client, api_key):
    """Test reservation confirmation."""
    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    res_resp = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    reservation_id = res_resp.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert "order_id" in data


def test_confirm_expired_reservation(client, api_key):
    """Test confirming an expired reservation."""
    from commerce_service.app import repo
    from datetime import datetime, timezone, timedelta

    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )

    # Create a reservation manually with old timestamp
    repo.adjust_stock("SKU-001", -50)
    repo.create_reservation("SKU-001", 50, "key-expired")

    # Update the created_at to 301 seconds ago
    conn = repo._get_connection()
    cursor = conn.cursor()
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = 1", (past_time,)
    )
    conn.commit()
    conn.close()

    # Try to confirm
    response = client.post(
        "/reservations/1/confirm",
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]


def test_confirm_non_pending_reservation(client, api_key):
    """Test confirming a non-PENDING reservation."""
    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    res_resp = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    reservation_id = res_resp.json()["id"]

    # Confirm once
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_header(api_key),
    )

    # Try to confirm again
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 400
    assert "not in PENDING state" in response.json()["detail"]


def test_cancel_reservation(client, api_key):
    """Test reservation cancellation."""
    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    res_resp = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    reservation_id = res_resp.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["stock_restored"] == 50


def test_cancel_non_pending_reservation(client, api_key):
    """Test cancelling a non-PENDING reservation."""
    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    res_resp = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=get_auth_header(api_key),
    )
    reservation_id = res_resp.json()["id"]

    # Confirm reservation
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_header(api_key),
    )

    # Try to cancel
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_auth_header(api_key),
    )
    assert response.status_code == 400
    assert "not in PENDING state" in response.json()["detail"]


def test_get_orders(client, api_key):
    """Test get orders endpoint."""
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 500},
        headers=get_auth_header(api_key),
    )

    # Create and confirm multiple orders
    for i in range(15):
        res_resp = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers=get_auth_header(api_key),
        )
        reservation_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_header(api_key),
        )

    # Get first page
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 15

    # Get second page
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["page"] == 2


def test_happy_path_workflow(client, api_key):
    """Test the complete happy path workflow."""
    # 1. Create SKU
    sku_resp = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers=get_auth_header(api_key),
    )
    assert sku_resp.status_code == 201

    # 2. Create reservation
    res_resp = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 25,
            "idempotency_key": "order-12345",
        },
        headers=get_auth_header(api_key),
    )
    assert res_resp.status_code == 201
    reservation_id = res_resp.json()["id"]

    # 3. Confirm reservation
    confirm_resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_header(api_key),
    )
    assert confirm_resp.status_code == 200
    order_id = confirm_resp.json()["order_id"]

    # 4. Get orders
    orders_resp = client.get("/orders?page=1&size=10")
    assert orders_resp.status_code == 200
    data = orders_resp.json()
    assert len(data["orders"]) == 1
    assert data["orders"][0]["id"] == order_id
    assert data["orders"][0]["sku"] == "WIDGET-001"
    assert data["orders"][0]["quantity"] == 25


def test_unauthorized_mutation_attempts(client):
    """Test that mutations fail without valid API key."""
    endpoints = [
        ("POST", "/skus", {"sku": "SKU-001", "initial_stock": 100}),
        ("POST", "/stock/adjust", {"sku": "SKU-001", "amount": 10}),
        ("POST", "/reservations", {
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "key-1",
        }),
        ("POST", "/reservations/1/confirm", None),
        ("POST", "/reservations/1/cancel", None),
    ]

    for method, path, data in endpoints:
        if method == "POST":
            response = client.post(path, json=data) if data else client.post(path)
            assert response.status_code in [401, 403], f"Failed for {method} {path}"
