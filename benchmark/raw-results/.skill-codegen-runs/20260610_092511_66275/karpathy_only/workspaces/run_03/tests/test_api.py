import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, get_repository


@pytest.fixture
def temp_db():
    _, path = tempfile.mkstemp(suffix=".db")
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture(autouse=True)
def reset_app(temp_db):
    from commerce_service.repository import Repository

    test_repo = Repository(temp_db)

    def override_get_repo():
        return test_repo

    app.dependency_overrides[get_repository] = override_get_repo
    yield test_repo
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    os.environ["API_KEY"] = "test-api-key-12345"
    return "test-api-key-12345"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_duplicate(client, api_key):
    response1 = client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response1.status_code == 201

    response2 = client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response2.status_code == 409


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 204


def test_adjust_stock_sku_not_found(client, api_key):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_create_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 5},
        headers={"X-API-Key": api_key},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["quantity"] == 10


def test_confirm_reservation_not_found(client, api_key):
    response = client.post(
        "/reservations/nonexistent-id/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 204


def test_cancel_reservation_not_found(client, api_key):
    response = client.post(
        "/reservations/nonexistent-id/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_list_orders_pagination(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 1000},
        headers={"X-API-Key": api_key},
    )

    # Create multiple orders
    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
            headers={"X-API-Key": api_key},
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    response = client.get("/orders?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["total"] == 5
    assert data["skip"] == 0
    assert data["limit"] == 2


def test_list_orders_with_offset(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 1000},
        headers={"X-API-Key": api_key},
    )

    # Create 5 orders
    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
            headers={"X-API-Key": api_key},
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    response = client.get("/orders?skip=3&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["skip"] == 3
    assert data["limit"] == 2


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_expired_reservation_rejection(client, api_key, reset_app):
    from datetime import datetime, timedelta

    test_repo = reset_app

    client.post(
        "/skus",
        json={"sku": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res.json()["reservation_id"]

    # Set reservation to expired
    now = datetime.utcnow()
    past = (now - timedelta(minutes=5)).isoformat()
    conn = test_repo._get_connection()
    conn.execute(
        "UPDATE reservations SET expires_at = ? WHERE id = ?", (past, reservation_id)
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 410
