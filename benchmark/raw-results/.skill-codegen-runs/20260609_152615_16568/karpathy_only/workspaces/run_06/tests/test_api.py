import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service import models
from src.commerce_service.app import app, get_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    os.environ["COMMERCE_API_KEY"] = "test-key-123"
    return "test-key-123"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU-001"
    assert data["stock_quantity"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 150


def test_adjust_stock_not_found(client, api_key):
    response = client.post(
        "/skus/999/adjust-stock",
        json={"quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_create_reservation_success(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert len(data["items"]) == 1


def test_create_reservation_insufficient_stock(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 30},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409


def test_reservation_idempotent_retry(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # First request
    response1 = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    # Retry with same idempotency key
    response2 = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    # Should return same reservation
    assert data1["id"] == data2["id"]


def test_confirm_reservation_success(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"


def test_confirm_reservation_not_found(client, api_key):
    response = client.post(
        "/reservations/res-nonexistent/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0


def test_list_orders_with_pagination(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create orders
    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={
                "idempotency_key": f"req-{i}",
                "items": [{"sku_id": sku_id, "quantity": 1}],
                "expiry_minutes": 30,
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res_response.json()["reservation_id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    response = client.get("/orders?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["skip"] == 0
    assert data["limit"] == 10

    response2 = client.get("/orders?skip=10&limit=10")
    data2 = response2.json()
    assert len(data2["items"]) == 5


def test_get_order(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "idempotency_key": "req-1",
            "items": [{"sku_id": sku_id, "quantity": 50}],
            "expiry_minutes": 30,
        },
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["reservation_id"]

    order_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    order_id = order_response.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["order_id"] == order_id
    assert response.json()["status"] == "CONFIRMED"


def test_get_order_not_found(client):
    response = client.get("/orders/ord-nonexistent")
    assert response.status_code == 404
