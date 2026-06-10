import os

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import DB_PATH, init_db


@pytest.fixture(autouse=True)
def setup_db():
    if DB_PATH.exists():
        os.remove(DB_PATH)
    init_db()
    yield
    if DB_PATH.exists():
        os.remove(DB_PATH)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    return "test-key-12345"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SKU-001"
    assert data["name"] == "Widget"
    assert data["current_stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 403


def test_create_sku_no_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 422


def test_adjust_stock_success(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/stock/adjust",
        json={"quantity": 50},
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["current_stock"] == 150


def test_adjust_stock_insufficient(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 10},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/stock/adjust",
        json={"quantity": -20},
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 400


def test_adjust_stock_not_found(client, api_key):
    response = client.post(
        "/skus/999/stock/adjust",
        json={"quantity": 10},
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 404


def test_create_reservation_success(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_idempotent(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    resp1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    resp2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    assert resp1.json()["id"] == resp2.json()["id"]


def test_create_reservation_insufficient_stock(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 10},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 20,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_confirm_reservation_success(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"
    assert data["order_id"] is not None


def test_confirm_reservation_expired(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 1,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_resp.json()["id"]

    import time
    time.sleep(1.1)

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 410


def test_confirm_reservation_unauthorized(client):
    response = client.post(
        "/reservations/1/confirm",
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 403


def test_cancel_reservation_success(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_resp.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": api_key},
    )

    response = client.get("/orders?offset=0&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["orders"]) == 1
    assert data["limit"] == 20
    assert data["offset"] == 0


def test_list_orders_pagination(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    for i in range(3):
        res_resp = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"idempotency-{i}",
                "ttl_seconds": 3600,
            },
            headers={"x-api-key": api_key},
        )
        reservation_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"x-api-key": api_key},
        )

    response = client.get("/orders?offset=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["orders"]) == 2

    response = client.get("/orders?offset=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 1


def test_get_order(client, api_key):
    sku_resp = client.post(
        "/skus",
        json={"code": "SKU-001", "name": "Widget", "initial_stock": 100},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "idempotency-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_resp.json()["id"]

    confirm_resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": api_key},
    )
    order_id = confirm_resp.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["reservation_id"] == reservation_id


def test_get_order_not_found(client):
    response = client.get("/orders/999")
    assert response.status_code == 404
