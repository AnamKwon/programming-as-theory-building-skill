"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app
from commerce_service.models import Base
from commerce_service.repository import get_db

# Create in-memory database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    """Override get_db dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

API_TOKEN = "test-secret-key-12345"
HEADERS = {"X-API-Token": API_TOKEN}


def test_health_check():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku():
    """Test SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-001", "initial_stock": 100},
        headers=HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "TEST-001"
    assert response.json()["initial_stock"] == 100


def test_create_sku_missing_token():
    """Test SKU creation without token."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-002", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_token():
    """Test SKU creation with invalid token."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-003", "initial_stock": 100},
        headers={"X-API-Token": "wrong-token"},
    )
    assert response.status_code == 401


def test_adjust_stock():
    """Test stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "TEST-004", "initial_stock": 50},
        headers=HEADERS,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-004", "amount": 10},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 60


def test_create_reservation_happy_path():
    """Test creating a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-005", "initial_stock": 100},
        headers=HEADERS,
    )

    response = client.post(
        "/reservations",
        json={"sku": "TEST-005", "quantity": 10, "idempotency_key": "idem-001"},
        headers=HEADERS,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-005"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "idem-001"
    assert data["id"] is not None


def test_create_reservation_insufficient_stock():
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-006", "initial_stock": 5},
        headers=HEADERS,
    )

    response = client.post(
        "/reservations",
        json={"sku": "TEST-006", "quantity": 10, "idempotency_key": "idem-002"},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent():
    """Test reservation idempotency."""
    client.post(
        "/skus",
        json={"sku": "TEST-007", "initial_stock": 100},
        headers=HEADERS,
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "TEST-007", "quantity": 10, "idempotency_key": "idem-003"},
        headers=HEADERS,
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "TEST-007", "quantity": 20, "idempotency_key": "idem-003"},
        headers=HEADERS,
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]
    assert data1["quantity"] == 10
    assert data2["quantity"] == 10


def test_confirm_reservation():
    """Test confirming a reservation."""
    sku_resp = client.post(
        "/skus",
        json={"sku": "TEST-008", "initial_stock": 100},
        headers=HEADERS,
    )

    reservation_resp = client.post(
        "/reservations",
        json={"sku": "TEST-008", "quantity": 15, "idempotency_key": "idem-004"},
        headers=HEADERS,
    )
    reservation_id = reservation_resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"


def test_confirm_reservation_not_pending():
    """Test confirming a non-pending reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-009", "initial_stock": 100},
        headers=HEADERS,
    )

    reservation_resp = client.post(
        "/reservations",
        json={"sku": "TEST-009", "quantity": 10, "idempotency_key": "idem-005"},
        headers=HEADERS,
    )
    reservation_id = reservation_resp.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
    assert response.status_code == 400


def test_cancel_reservation():
    """Test cancelling a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-010", "initial_stock": 100},
        headers=HEADERS,
    )

    reservation_resp = client.post(
        "/reservations",
        json={"sku": "TEST-010", "quantity": 20, "idempotency_key": "idem-006"},
        headers=HEADERS,
    )
    reservation_id = reservation_resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_not_pending():
    """Test cancelling a non-pending reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-011", "initial_stock": 100},
        headers=HEADERS,
    )

    reservation_resp = client.post(
        "/reservations",
        json={"sku": "TEST-011", "quantity": 10, "idempotency_key": "idem-007"},
        headers=HEADERS,
    )
    reservation_id = reservation_resp.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=HEADERS,
    )
    assert response.status_code == 400


def test_get_orders_paginated():
    """Test paginated orders retrieval."""
    client.post(
        "/skus",
        json={"sku": "TEST-012", "initial_stock": 200},
        headers=HEADERS,
    )

    for i in range(5):
        reservation_resp = client.post(
            "/reservations",
            json={"sku": "TEST-012", "quantity": 10, "idempotency_key": f"idem-paginated-{i}"},
            headers=HEADERS,
        )
        reservation_id = reservation_resp.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    response = client.get("/orders?page=1&size=2", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 2
    assert len(data["orders"]) == 2

    response_page2 = client.get("/orders?page=2&size=2", headers=HEADERS)
    assert len(response_page2.json()["orders"]) == 2

    response_page3 = client.get("/orders?page=3&size=2", headers=HEADERS)
    assert len(response_page3.json()["orders"]) == 1


def test_complete_workflow():
    """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
    sku_response = client.post(
        "/skus",
        json={"sku": "WORKFLOW-001", "initial_stock": 50},
        headers=HEADERS,
    )
    assert sku_response.status_code == 201

    reservation_response = client.post(
        "/reservations",
        json={"sku": "WORKFLOW-001", "quantity": 5, "idempotency_key": "workflow-idem-001"},
        headers=HEADERS,
    )
    assert reservation_response.status_code == 201
    reservation = reservation_response.json()
    assert reservation["status"] == "PENDING"

    confirm_response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=HEADERS,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"

    orders_response = client.get("/orders?page=1&size=10", headers=HEADERS)
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert orders["total"] == 1
    assert orders["orders"][0]["sku"] == "WORKFLOW-001"
    assert orders["orders"][0]["quantity"] == 5
