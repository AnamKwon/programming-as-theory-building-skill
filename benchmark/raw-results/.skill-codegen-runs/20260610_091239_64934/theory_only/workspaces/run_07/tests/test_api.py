import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, db, service


@pytest.fixture(autouse=True)
def setup_test_db():
    os.environ["API_KEY"] = "test-key-123"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    db.db_path = test_db_path
    db.init_schema()

    yield

    if os.path.exists(test_db_path):
        os.unlink(test_db_path)


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["name"] == "Test Product"
    assert data["stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    response = client.put(
        "/skus/1/stock",
        json={"adjustment": 50},
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 150


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={
            "order_id": "ORDER-001",
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "IDEMPOTENCY-001",
        },
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["order_id"] == "ORDER-001"
    assert data["status"] == "pending"
    assert data["quantity"] == 50


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={
            "order_id": "ORDER-001",
            "sku_id": 1,
            "quantity": 150,
            "idempotency_key": "IDEMPOTENCY-001",
        },
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_idempotent_reservation_retry(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    response1 = client.post(
        "/reservations",
        json={
            "order_id": "ORDER-001",
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "IDEMPOTENCY-001",
        },
        headers={"X-Api-Key": "test-key-123"},
    )
    res_id_1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={
            "order_id": "ORDER-001",
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "IDEMPOTENCY-001",
        },
        headers={"X-Api-Key": "test-key-123"},
    )
    res_id_2 = response2.json()["id"]

    assert res_id_1 == res_id_2
    assert response1.status_code == 201
    assert response2.status_code == 201


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={
            "order_id": "ORDER-001",
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "IDEMPOTENCY-001",
        },
        headers={"X-Api-Key": "test-key-123"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={
            "order_id": "ORDER-001",
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "IDEMPOTENCY-001",
        },
        headers={"X-Api-Key": "test-key-123"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 1000},
        headers={"X-Api-Key": "test-key-123"},
    )

    for i in range(10):
        client.post(
            "/reservations",
            json={
                "order_id": f"ORDER-{i:03d}",
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": f"IDEMPOTENCY-{i:03d}",
            },
            headers={"X-Api-Key": "test-key-123"},
        )

    response = client.get(
        "/orders?limit=5&offset=0",
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 10
    assert data["limit"] == 5
    assert data["offset"] == 0


def test_list_orders_unauthorized(client):
    response = client.get(
        "/orders",
        headers={"X-Api-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_expired_reservation_rejection(client):
    import tempfile
    from datetime import datetime, timedelta

    from commerce_service.repository import Database

    client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-Api-Key": "test-key-123"},
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = Database(f.name)

    expires_at = datetime.utcnow() - timedelta(minutes=1)
    res_id = test_db.create_reservation(
        "ORDER-001",
        1,
        50,
        "IDEMPOTENCY-001",
        expires_at,
    )
    test_db.reserve_stock(1, 50)

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-Api-Key": "test-key-123"},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]
