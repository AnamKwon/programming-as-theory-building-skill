"""Integration tests for the API endpoints."""

import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base, CreateSKURequest

DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    """Override get_db for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

VALID_API_KEY = "test-api-key"
INVALID_API_KEY = "invalid-key"


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_without_auth():
    """Test creating SKU without authentication fails."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_with_invalid_auth():
    """Test creating SKU with invalid auth key fails."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": f"Bearer {INVALID_API_KEY}"},
    )
    assert response.status_code == 403


def test_create_sku_success():
    """Test creating a SKU successfully."""
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": f"Bearer {VALID_API_KEY}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["stock"] == 100


def test_create_duplicate_sku():
    """Test creating duplicate SKU fails."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}
    client.post(
        "/skus",
        json={"sku": "SKU002", "initial_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/skus",
        json={"sku": "SKU002", "initial_stock": 50},
        headers=headers,
    )
    assert response.status_code == 400


def test_adjust_stock_success():
    """Test adjusting stock successfully."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU003", "initial_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU003", "amount": 50},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 150


def test_adjust_stock_negative():
    """Test adjusting stock with negative amount."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU004", "initial_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU004", "amount": -30},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 70


def test_create_reservation_insufficient_stock():
    """Test creating reservation with insufficient stock fails."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU005", "initial_stock": 10},
        headers=headers,
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU005", "quantity": 20, "idempotency_key": "key001"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_success():
    """Test creating a reservation successfully."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU006", "initial_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU006", "quantity": 25, "idempotency_key": "key002"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU006"
    assert data["quantity"] == 25
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key002"


def test_reservation_idempotency():
    """Test that idempotent retries return the same reservation without deducting stock twice."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU007", "initial_stock": 100},
        headers=headers,
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU007", "quantity": 10, "idempotency_key": "key003"},
        headers=headers,
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU007", "quantity": 10, "idempotency_key": "key003"},
        headers=headers,
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["idempotency_key"] == data2["idempotency_key"]

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU007", "amount": 0},
        headers=headers,
    )
    assert sku_response.json()["stock"] == 90


def test_confirm_reservation_success():
    """Test confirming a reservation successfully."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU008", "initial_stock": 100},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU008", "quantity": 15, "idempotency_key": "key004"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_expired():
    """Test confirming an expired reservation fails and restores stock."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU009", "initial_stock": 100},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU009", "quantity": 20, "idempotency_key": "key005"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    time.sleep(301)

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU009", "amount": 0},
        headers=headers,
    )
    assert sku_response.json()["stock"] == 100


def test_confirm_reservation_not_pending():
    """Test confirming a non-PENDING reservation fails."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU010", "initial_stock": 100},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU010", "quantity": 10, "idempotency_key": "key006"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400
    assert "Cannot confirm reservation" in response.json()["detail"]


def test_cancel_reservation_success():
    """Test canceling a reservation successfully."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU011", "initial_stock": 100},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU011", "quantity": 25, "idempotency_key": "key007"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU011", "amount": 0},
        headers=headers,
    )
    assert sku_response.json()["stock"] == 100


def test_list_orders_empty():
    """Test listing orders when none exist."""
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_orders_pagination():
    """Test listing orders with pagination."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    client.post(
        "/skus",
        json={"sku": "SKU012", "initial_stock": 1000},
        headers=headers,
    )

    reservation_ids = []
    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU012", "quantity": 10, "idempotency_key": f"key_order_{i}"},
            headers=headers,
        )
        reservation_ids.append(res_response.json()["id"])

    for rid in reservation_ids:
        client.post(f"/reservations/{rid}/confirm", headers=headers)

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 10
    assert data1["page"] == 1
    assert data1["size"] == 10
    assert data1["total"] == 15

    response2 = client.get("/orders?page=2&size=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 5
    assert data2["page"] == 2


def test_happy_path_workflow():
    """Test the complete happy path: Create SKU -> Reserve -> Confirm -> List Orders."""
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    sku_response = client.post(
        "/skus",
        json={"sku": "WORKFLOW_SKU", "initial_stock": 50},
        headers=headers,
    )
    assert sku_response.status_code == 201

    res_response = client.post(
        "/reservations",
        json={"sku": "WORKFLOW_SKU", "quantity": 5, "idempotency_key": "workflow_key"},
        headers=headers,
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    orders_response = client.get("/orders?page=1&size=10")
    assert orders_response.status_code == 200
    orders = orders_response.json()["items"]
    assert len(orders) > 0
    assert any(order["id"] == order_id for order in orders)
