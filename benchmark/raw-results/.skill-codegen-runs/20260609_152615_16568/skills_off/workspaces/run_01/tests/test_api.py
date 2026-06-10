import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from commerce_service.models import Base
from commerce_service.app import app, get_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def set_test_api_key(monkeypatch):
    monkeypatch.setenv("COMMERCE_API_KEY", "test-key-123")


def test_health_check(client):
    response = client.post("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A", "description": "A test product"},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "SKU001"
    assert data["name"] == "Product A"
    assert data["description"] == "A test product"


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
    )
    assert response.status_code == 403
    assert "API key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_create_sku_duplicate(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product B"},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 409


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.patch(
        "/stock/SKU001",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 100

    response = client.patch(
        "/stock/SKU001",
        json={"quantity": 50},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 150


def test_adjust_stock_sku_not_found(client):
    response = client.patch(
        "/stock/NON_EXISTENT",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/stock/SKU001",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 50
    assert data["status"] == "pending"
    assert data["id"] is not None


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/stock/SKU001",
        json={"quantity": 30},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/stock/SKU001",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": "test-key-123"},
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": "test-key-123"},
    )

    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]
    assert data1["idempotency_key"] == data2["idempotency_key"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/stock/SKU001",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": "test-key-123"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["confirmed_at"] is not None


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/non-existent-id/confirm",
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 404


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/stock/SKU001",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": "test-key-123"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_reservation_not_found(client):
    response = client.post(
        "/reservations/non-existent-id/cancel",
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 404


def test_list_orders(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert "orders" in data
    assert "total" in data
    assert "skip" in data
    assert "limit" in data
    assert data["skip"] == 0
    assert data["limit"] == 10
    assert data["total"] == 0


def test_list_orders_pagination(client):
    response = client.get("/orders?skip=5&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["skip"] == 5
    assert data["limit"] == 20


def test_unauthorized_mutation_endpoints(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product A"},
    )
    assert response.status_code == 403

    response = client.patch(
        "/stock/SKU001",
        json={"quantity": 100},
    )
    assert response.status_code == 403

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
    )
    assert response.status_code == 403
