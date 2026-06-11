"""API endpoint tests."""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from src.commerce_service.app import app, repository, service
from src.commerce_service.models import Base
from src.commerce_service.security import VALID_API_KEY


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    Base.metadata.drop_all(repository.engine)
    Base.metadata.create_all(repository.engine)
    yield
    Base.metadata.drop_all(repository.engine)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def headers():
    """Create headers with valid API key."""
    return {"X-API-Key": VALID_API_KEY}


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, headers):
    """Test creating a SKU."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-001", "initial_stock": 100},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-001"
    assert data["stock"] == 100


def test_create_sku_missing_auth(client):
    """Test creating SKU without auth key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-002", "initial_stock": 50},
    )
    assert response.status_code == 401
    assert "Missing API key" in response.json()["detail"]


def test_create_sku_invalid_auth(client):
    """Test creating SKU with invalid auth key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-003", "initial_stock": 75},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]


def test_adjust_stock(client, headers):
    """Test adjusting stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-004", "initial_stock": 100},
        headers=headers,
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-004", "amount": 25},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "TEST-SKU-004"
    assert data["new_stock"] == 125


def test_adjust_stock_decrease(client, headers):
    """Test decreasing stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-005", "initial_stock": 100},
        headers=headers,
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-005", "amount": -40},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_stock"] == 60


def test_create_reservation_success(client, headers):
    """Test creating a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-006", "initial_stock": 200},
        headers=headers,
    )
    response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-006", "quantity": 50, "idempotency_key": "key-001"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-006"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, headers):
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-007", "initial_stock": 50},
        headers=headers,
    )
    response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-007", "quantity": 100, "idempotency_key": "key-002"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_reservation_idempotency(client, headers):
    """Test idempotent reservations."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-008", "initial_stock": 200},
        headers=headers,
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-008", "quantity": 30, "idempotency_key": "key-003"},
        headers=headers,
    )
    assert response1.status_code == 201
    res1_id = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-008", "quantity": 30, "idempotency_key": "key-003"},
        headers=headers,
    )
    assert response2.status_code == 200
    res2_id = response2.json()["id"]

    assert res1_id == res2_id


def test_confirm_reservation_success(client, headers):
    """Test confirming a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-009", "initial_stock": 200},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-009", "quantity": 40, "idempotency_key": "key-004"},
        headers=headers,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["order_id"] is not None


def test_confirm_non_pending_reservation(client, headers):
    """Test confirming a non-pending reservation fails."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-010", "initial_stock": 200},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-010", "quantity": 50, "idempotency_key": "key-005"},
        headers=headers,
    )
    res_id = res_response.json()["id"]

    client.post(f"/reservations/{res_id}/confirm", headers=headers)

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400


def test_reservation_expiration(client, headers):
    """Test that expired reservations cannot be confirmed."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-011", "initial_stock": 200},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-011", "quantity": 60, "idempotency_key": "key-006"},
        headers=headers,
    )
    res_id = res_response.json()["id"]

    reservation = service.repo.get_reservation_by_id(res_id)
    reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
    session = service.repo.get_session()
    try:
        session.merge(reservation)
        session.commit()
    finally:
        session.close()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]

    expired_res = service.repo.get_reservation_by_id(res_id)
    assert expired_res.status == "EXPIRED"

    sku = service.repo.get_sku_by_name("TEST-SKU-011")
    assert sku.stock == 200


def test_cancel_reservation_success(client, headers):
    """Test cancelling a reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-012", "initial_stock": 200},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-012", "quantity": 35, "idempotency_key": "key-007"},
        headers=headers,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    sku = service.repo.get_sku_by_name("TEST-SKU-012")
    assert sku.stock == 200


def test_cancel_non_pending_reservation(client, headers):
    """Test cancelling a non-pending reservation fails."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-013", "initial_stock": 200},
        headers=headers,
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-SKU-013", "quantity": 45, "idempotency_key": "key-008"},
        headers=headers,
    )
    res_id = res_response.json()["id"]

    client.post(f"/reservations/{res_id}/confirm", headers=headers)

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 400


def test_get_orders_paginated(client, headers):
    """Test getting paginated orders."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-014", "initial_stock": 500},
        headers=headers,
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "TEST-SKU-014",
                "quantity": 5,
                "idempotency_key": f"key-{5000+i}",
            },
            headers=headers,
        )
        res_id = res_response.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers=headers)

    response = client.get("/orders?page=1&size=10", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25

    response = client.get("/orders?page=3&size=10", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_happy_path_workflow(client, headers):
    """Test complete happy path: SKU -> Reserve -> Confirm -> List Orders."""
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 1000},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 100, "idempotency_key": "order-001"},
        headers=headers,
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["order_id"]

    orders_response = client.get("/orders?page=1&size=10", headers=headers)
    assert orders_response.status_code == 200
    orders = orders_response.json()["items"]
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
