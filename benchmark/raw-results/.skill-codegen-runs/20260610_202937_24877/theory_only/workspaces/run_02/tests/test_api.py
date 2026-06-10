import pytest
import os
from fastapi.testclient import TestClient
from src.commerce_service.app import app, db, service
from datetime import datetime, timezone, timedelta


@pytest.fixture(autouse=True)
def reset_db():
    db.clear_all()
    yield
    db.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"
    assert response.json()["available_stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "wrong-token"},
    )
    assert response.status_code == 401
    assert "Invalid API token" in response.json()["detail"]


def test_create_sku_missing_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert "Missing API token" in response.json()["detail"]


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_adjust_stock_not_found(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 50},
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 404
    assert "SKU not found" in response.json()["detail"]


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Token": "test-token-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 100,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"
    assert data["id"] is not None


def test_create_reservation_idempotent_retry(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["created_at"] == data2["created_at"]
    assert response2.status_code == 201

    sku_response = client.get("/health")
    assert sku_response.status_code == 200


def test_confirm_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["order_id"] is not None


def test_confirm_reservation_expired(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    reservation_id = res_response.json()["id"]

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]

    reservation = db.get_reservation(reservation_id)
    assert reservation["status"] == "EXPIRED"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["restored_stock"] == 30


def test_cancel_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "key1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": "test-token-12345"},
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Token": "test-token-12345"},
    )
    assert response.status_code == 400
    assert "not pending" in response.json()["detail"]


def test_get_orders_paginated(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Token": "test-token-12345"},
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 10,
                "idempotency_key": f"key{i}",
            },
            headers={"X-API-Token": "test-token-12345"},
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": "test-token-12345"},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 15
    assert data["page"] == 2


def test_full_workflow(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET", "initial_stock": 100},
        headers={"X-API-Token": "test-token-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "WIDGET",
            "quantity": 25,
            "idempotency_key": "order1",
        },
        headers={"X-API-Token": "test-token-12345"},
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": "test-token-12345"},
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["order_id"]

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == order_id
    assert data["items"][0]["sku"] == "WIDGET"
    assert data["items"][0]["quantity"] == 25
