import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def client(temp_db, monkeypatch):
    # Override the database path in the app's repository
    monkeypatch.setattr("src.commerce_service.app.repository", Repository(db_path=temp_db))
    # Re-initialize the service with the new repository
    from src.commerce_service.service import CommerceService
    monkeypatch.setattr("src.commerce_service.app.service", CommerceService(Repository(db_path=temp_db)))

    # Set a known API token
    monkeypatch.setenv("API_TOKEN", "test-token")
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_no_auth_required(client):
    # Health check should work without API token
    response = client.get("/health")
    assert response.status_code == 200


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_duplicate(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 409


def test_create_sku_no_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "wrong-token"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 150


def test_adjust_stock_negative(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70


def test_adjust_stock_nonexistent_sku(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 10},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key-1"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 150, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["reservation_id"] == res_id


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 404


def test_confirm_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": "test-token"},
    )

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 400


def test_confirm_reservation_expired(client, monkeypatch):
    from datetime import datetime, timedelta

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    res_id = res.json()["id"]

    # Manually expire the reservation
    from src.commerce_service.app import repository
    conn = repository._get_connection()
    cursor = conn.cursor()
    expired_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (expired_time, res_id))
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_not_found(client):
    response = client.post(
        "/reservations/999/cancel",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 404


def test_cancel_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Token": "test-token"},
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": "test-token"},
    )

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Token": "test-token"},
    )
    assert response.status_code == 400


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Token": "test-token"},
    )

    # Create 25 orders
    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Token": "test-token"},
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": "test-token"},
        )

    # Test pagination
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["size"] == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25

    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["total"] == 25


def test_unauthorized_mutations(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 10},
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key"},
    )
    assert response.status_code == 401


def test_happy_path_workflow(client):
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"sku": "PROD123", "initial_stock": 500},
        headers={"X-API-Token": "test-token"},
    )
    assert sku_response.status_code == 201

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "PROD123", "quantity": 100, "idempotency_key": "order-abc"},
        headers={"X-API-Token": "test-token"},
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": "test-token"},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"

    # Get orders
    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert data["total"] == 1
    assert len(data["orders"]) == 1
