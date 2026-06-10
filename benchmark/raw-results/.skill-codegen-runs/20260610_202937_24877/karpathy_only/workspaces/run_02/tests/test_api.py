"""Integration tests for API endpoints."""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from src.commerce_service.app import app
from src.commerce_service.repository import Repository, ReservationRecord
from src.commerce_service.service import CommerceService
import src.commerce_service.app as app_module

VALID_API_KEY = "test-api-key-12345"
INVALID_API_KEY = "invalid-key"


@pytest.fixture(autouse=True)
def setup_db():
    """Reset database before each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db_url = f"sqlite:///{db_path}"
        repo = Repository(db_url)
        service = CommerceService(repo)
        app_module.repo = repo
        app_module.service = service
        yield
        app_module.repo = Repository("sqlite:///commerce.db")
        app_module.service = CommerceService(app_module.repo)


def get_client():
    """Get a test client."""
    return TestClient(app)


def test_health_check():
    """Test health endpoint - no auth required."""
    client = get_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_missing_auth():
    """Test SKU creation without API key."""
    client = get_client()
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth():
    """Test SKU creation with invalid API key."""
    client = get_client()
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": INVALID_API_KEY},
    )
    assert response.status_code == 401


def test_create_sku_valid():
    """Test successful SKU creation."""
    client = get_client()
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_adjust_stock():
    """Test stock adjustment."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU", "amount": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_create_reservation():
    """Test reservation creation (happy path)."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert "id" in data


def test_create_reservation_insufficient_stock():
    """Test reservation creation with insufficient stock."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 30},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-2"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency():
    """Test idempotent reservation creation."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    idempotency_key = "unique-key-3"

    response1 = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": idempotency_key},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": idempotency_key},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"]


def test_confirm_reservation():
    """Test reservation confirmation."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-4"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["order_id"] > 0


def test_confirm_reservation_expired():
    """Test confirmation of expired reservation."""
    client = get_client()

    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-5"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    session = app_module.repo.get_session()
    reservation = session.query(ReservationRecord).filter(ReservationRecord.id == reservation_id).first()
    past_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=301)
    reservation.created_at = past_time
    session.commit()
    session.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_confirm_reservation_invalid_state():
    """Test confirmation of reservation in invalid state."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-6"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400


def test_cancel_reservation():
    """Test reservation cancellation."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-7"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock():
    """Test that cancellation restores stock."""
    client = get_client()

    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU", "quantity": 50, "idempotency_key": "unique-key-8"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    sku_before = app_module.repo.get_sku("TEST-SKU")
    assert sku_before.available_stock == 50
    assert sku_before.reserved_stock == 50

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )

    sku_after = app_module.repo.get_sku("TEST-SKU")
    assert sku_after.available_stock == 100
    assert sku_after.reserved_stock == 0


def test_list_orders_pagination():
    """Test orders list pagination."""
    client = get_client()
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY},
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "TEST-SKU", "quantity": 10, "idempotency_key": f"unique-key-{100+i}"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

    response_page1 = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response_page1.status_code == 200
    data1 = response_page1.json()
    assert len(data1["items"]) == 10
    assert data1["total"] == 15
    assert data1["page"] == 1
    assert data1["size"] == 10

    response_page2 = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response_page2.status_code == 200
    data2 = response_page2.json()
    assert len(data2["items"]) == 5
    assert data2["page"] == 2


def test_list_orders_requires_auth():
    """Test that orders list requires authentication."""
    client = get_client()
    response = client.get("/orders")
    assert response.status_code == 401
