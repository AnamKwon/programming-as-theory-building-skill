import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from commerce_service.app import app, _service, _repo
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture(autouse=True)
def reset_db():
    conn = _repo._get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM reservations")
        cursor.execute("DELETE FROM skus")
        conn.commit()
    except Exception:
        conn.rollback()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_api_key():
    return "test-key-12345"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_create_sku_with_auth(client, valid_api_key):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["initial_stock"] == 100


def test_create_sku_without_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403
    assert "Invalid or missing API key" in response.json()["detail"]


def test_create_sku_invalid_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_with_auth(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 50},
        headers={"X-API-Key": valid_api_key},
    )
    response = client.post(
        "/inventory/SKU-001/adjust",
        json={"quantity": 25},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["adjustment"] == 25


def test_adjust_stock_without_auth(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 50},
        headers={"X-API-Key": valid_api_key},
    )
    response = client.post(
        "/inventory/SKU-001/adjust",
        json={"quantity": 25},
    )
    assert response.status_code == 403


def test_adjust_stock_nonexistent_sku(client, valid_api_key):
    response = client.post(
        "/inventory/SKU-MISSING/adjust",
        json={"quantity": 10},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_create_reservation_happy_path(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["units"] == 25
    assert data["state"] == "pending"
    assert "reservation_id" in data
    assert "expires_at" in data


def test_create_reservation_insufficient_stock(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 10},
        headers={"X-API-Key": valid_api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 50, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent_retry(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_create_reservation_without_auth(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
    )
    assert response.status_code == 403


def test_get_reservation(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    create_resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = create_resp.json()["reservation_id"]

    response = client.get(f"/reservations/{reservation_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert data["state"] == "pending"


def test_confirm_reservation_happy_path(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    create_resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = create_resp.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["units"] == 25
    assert "order_id" in data


def test_confirm_reservation_without_auth(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    create_resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = create_resp.json()["reservation_id"]

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 403


def test_cancel_reservation_happy_path(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    create_resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = create_resp.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_cancel_reservation_without_auth(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )
    create_resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = create_resp.json()["reservation_id"]

    response = client.post(f"/reservations/{reservation_id}/cancel")
    assert response.status_code == 403


def test_get_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["orders"] == []
    assert data["pagination"]["total"] == 0


def test_get_orders_with_pagination(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 1000},
        headers={"X-API-Key": valid_api_key},
    )

    for i in range(15):
        create_resp = client.post(
            "/reservations",
            json={"sku": "SKU-001", "units": 10, "idempotency_key": f"idem-{i}"},
            headers={"X-API-Key": valid_api_key},
        )
        reservation_id = create_resp.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": valid_api_key},
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["pagination"]["total"] == 15
    assert data["pagination"]["limit"] == 10
    assert data["pagination"]["offset"] == 0

    response = client.get("/orders?limit=10&offset=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["pagination"]["total"] == 15


def test_get_orders_invalid_limit(client):
    response = client.get("/orders?limit=0")
    assert response.status_code == 400

    response = client.get("/orders?limit=101")
    assert response.status_code == 400


def test_stock_accounting_invariant(client, valid_api_key):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": valid_api_key},
    )

    create_resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "units": 30, "idempotency_key": "idem-1"},
        headers={"X-API-Key": valid_api_key},
    )
    reservation_id = create_resp.json()["reservation_id"]

    on_hand, reserved = _service.repo.get_sku("SKU-001")
    assert on_hand == 100
    assert reserved == 30
    assert on_hand + reserved == 130

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": valid_api_key},
    )

    on_hand, reserved = _service.repo.get_sku("SKU-001")
    assert on_hand == 100
    assert reserved == 0
    assert on_hand + reserved == 100
