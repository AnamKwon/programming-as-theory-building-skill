"""Tests for the API endpoints."""

import pytest

API_KEY_HEADER = {"X-API-Key": "test-api-key"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"name": "TestWidget", "price": 19.99},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "TestWidget"
    assert data["price"] == 19.99
    assert "id" in data


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "TestWidget", "price": 19.99},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "TestWidget", "price": 19.99},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client):
    # Create SKU first
    sku_response = client.post(
        "/skus",
        json={"name": "AdjustWidget", "price": 15.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    # Adjust stock
    response = client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 50},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_quantity"] == 50
    assert data["reserved_quantity"] == 0


def test_create_reservation_success(client):
    # Setup: Create SKU and adjust stock
    sku_response = client.post(
        "/skus",
        json={"name": "ReservWidget", "price": 12.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 100},
        headers=API_KEY_HEADER,
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-idempotency-1",
        },
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
    assert data["status"] == "pending"
    assert "expires_at" in data


def test_create_reservation_insufficient_stock(client):
    # Setup: Create SKU with limited stock
    sku_response = client.post(
        "/skus",
        json={"name": "LimitWidget", "price": 10.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 5},
        headers=API_KEY_HEADER,
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-idempotency-2",
        },
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "IdempWidget", "price": 9.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 100},
        headers=API_KEY_HEADER,
    )

    # Create reservation twice with same idempotency key
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotent-key",
        },
        headers=API_KEY_HEADER,
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotent-key",
        },
        headers=API_KEY_HEADER,
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation_success(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "ConfirmWidget", "price": 8.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 100},
        headers=API_KEY_HEADER,
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "confirm-key",
        },
        headers=API_KEY_HEADER,
    )
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"


def test_cancel_reservation_success(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "CancelWidget", "price": 7.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 100},
        headers=API_KEY_HEADER,
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "cancel-key",
        },
        headers=API_KEY_HEADER,
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        json={},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_list_orders_pagination(client):
    # Setup: Create SKU and multiple orders
    sku_response = client.post(
        "/skus",
        json={"name": "PaginationWidget", "price": 6.99},
        headers=API_KEY_HEADER,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"quantity": 1000},
        headers=API_KEY_HEADER,
    )

    # Create and confirm 5 reservations
    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"page-key-{i}",
            },
            headers=API_KEY_HEADER,
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=API_KEY_HEADER,
        )

    # Test pagination
    response = client.get(
        "/orders?skip=0&limit=2",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    response2 = client.get(
        "/orders?skip=2&limit=2",
        headers=API_KEY_HEADER,
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 2


def test_list_orders_requires_api_key(client):
    response = client.get("/orders")
    assert response.status_code == 403


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"name": "NoKeyWidget", "price": 5.99},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403
    assert "Invalid or missing API key" in response.json()["detail"]
