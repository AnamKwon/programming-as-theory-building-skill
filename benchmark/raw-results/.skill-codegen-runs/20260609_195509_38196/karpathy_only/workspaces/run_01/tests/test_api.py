"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_with_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "WIDGET-001"
    assert data["quantity_available"] == 100


def test_create_sku_without_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
    )
    assert response.status_code == 403


def test_create_sku_with_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_create_duplicate_sku_name(client):
    headers = {"X-API-Key": "test-key-123"}
    client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers,
    )
    response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 50},
        headers=headers,
    )
    assert response.status_code == 409


def test_adjust_stock(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.patch(
        f"/skus/{sku_id}/stock",
        json={"quantity_delta": 50},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["quantity_available"] == 150


def test_adjust_stock_nonexistent_sku(client):
    headers = {"X-API-Key": "test-key-123"}
    response = client.patch(
        "/skus/999/stock",
        json={"quantity_delta": 50},
        headers=headers,
    )
    assert response.status_code == 404


def test_create_reservation_sufficient_stock(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["quantity"] == 30


def test_create_reservation_insufficient_stock(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 50},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 100,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers,
    )
    assert response.status_code == 409


def test_idempotent_reservation_retry(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    res1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers,
    ).json()

    res2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers,
    ).json()

    assert res1["id"] == res2["id"]


def test_confirm_reservation(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    res = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers,
    ).json()

    response = client.post(
        f"/reservations/{res['id']}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    res = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers,
    ).json()

    response = client.post(
        f"/reservations/{res['id']}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_with_pagination(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 1000},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    for i in range(15):
        client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"res-key-{i}",
                "ttl_seconds": 300,
            },
            headers=headers,
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 15
    assert data["limit"] == 10
    assert data["offset"] == 0

    response = client.get("/orders?limit=10&offset=10")
    data = response.json()
    assert len(data["orders"]) == 5


def test_unauthorized_mutation_endpoints(client):
    headers_invalid = {"X-API-Key": "invalid-key"}

    response = client.post(
        "/skus",
        json={"name": "WIDGET-001", "quantity_available": 100},
        headers=headers_invalid,
    )
    assert response.status_code == 403

    response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 30,
            "idempotency_key": "res-key-1",
            "ttl_seconds": 300,
        },
        headers=headers_invalid,
    )
    assert response.status_code == 403
