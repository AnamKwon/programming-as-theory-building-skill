"""API endpoint tests."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.app import app, get_db


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """Create a test client with overridden dependency."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def api_key_headers():
    """API key headers for authenticated requests."""
    return {"X-API-Key": "test-key"}


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, api_key_headers):
    """Test SKU creation endpoint."""
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_available": 100},
        headers=api_key_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU-001"
    assert data["stock_available"] == 100


def test_create_sku_without_api_key(client):
    """Test that creating SKU without API key fails."""
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_available": 100},
    )
    assert response.status_code == 403


def test_create_sku_with_wrong_api_key(client):
    """Test that creating SKU with wrong API key fails."""
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_create_duplicate_sku(client, api_key_headers):
    """Test that duplicate SKU codes return 409."""
    client.post(
        "/skus",
        json={"sku_code": "SKU-002", "stock_available": 100},
        headers=api_key_headers,
    )
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-002", "stock_available": 50},
        headers=api_key_headers,
    )
    assert response.status_code == 409


def test_adjust_stock(client, api_key_headers):
    """Test stock adjustment endpoint."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-003", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"quantity_delta": 50},
        headers=api_key_headers,
    )
    assert response.status_code == 200
    assert response.json()["stock_available"] == 150


def test_adjust_stock_below_zero(client, api_key_headers):
    """Test that adjusting stock below zero fails."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-004", "stock_available": 50},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"quantity_delta": -60},
        headers=api_key_headers,
    )
    assert response.status_code == 400


def test_create_reservation_success(client, api_key_headers):
    """Test successful reservation creation."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-005", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 300,
        },
        headers=api_key_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["quantity"] == 30


def test_create_reservation_insufficient_stock(client, api_key_headers):
    """Test reservation with insufficient stock."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-006", "stock_available": 50},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 100,
            "idempotency_key": "idempotency-2",
            "ttl_seconds": 300,
        },
        headers=api_key_headers,
    )
    assert response.status_code == 400


def test_create_reservation_idempotent(client, api_key_headers):
    """Test idempotent reservation creation."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-007", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    payload = {
        "sku_id": sku_id,
        "quantity": 30,
        "idempotency_key": "idempotency-3",
        "ttl_seconds": 300,
    }

    res1 = client.post("/reservations", json=payload, headers=api_key_headers)
    res2 = client.post("/reservations", json=payload, headers=api_key_headers)

    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation_success(client, api_key_headers):
    """Test successful reservation confirmation."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-008", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "idempotency-4",
            "ttl_seconds": 300,
        },
        headers=api_key_headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=api_key_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"  # order status


def test_confirm_expired_reservation(client, api_key_headers):
    """Test confirming expired reservation fails."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-009", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "idempotency-5",
            "ttl_seconds": -1,  # already expired
        },
        headers=api_key_headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=api_key_headers,
    )
    assert response.status_code == 400


def test_cancel_reservation_success(client, api_key_headers):
    """Test successful reservation cancellation."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-010", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "idempotency-6",
            "ttl_seconds": 300,
        },
        headers=api_key_headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=api_key_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_order_success(client, api_key_headers):
    """Test getting an order."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-011", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "idempotency-7",
            "ttl_seconds": 300,
        },
        headers=api_key_headers,
    )
    reservation_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=api_key_headers,
    )
    order_id = order_response.json()["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_list_orders_pagination(client, api_key_headers):
    """Test order listing with pagination."""
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-012", "stock_available": 100},
        headers=api_key_headers,
    )
    sku_id = sku_response.json()["id"]

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"idempotency-pag-{i}",
                "ttl_seconds": 300,
            },
            headers=api_key_headers,
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=api_key_headers,
        )

    response = client.get("/orders?offset=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["offset"] == 0
    assert data["limit"] == 2

    response = client.get("/orders?offset=4&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
