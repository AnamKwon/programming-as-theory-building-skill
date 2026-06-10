import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield f"sqlite:///{db_path}"


@pytest.fixture
def client(temp_db, monkeypatch):
    repo = Repository(db_url=temp_db)
    service = CommerceService(repo)
    monkeypatch.setattr("commerce_service.app.repo", repo)
    monkeypatch.setattr("commerce_service.app.service", service)
    return TestClient(app)


@pytest.fixture
def api_key():
    return "sk-test-key-12345"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["name"] == "Widget"
    assert data["current_stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_duplicate_sku(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Another Widget", "initial_stock": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_adjust_stock(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.patch(
        "/skus/SKU001/stock",
        json={"delta": -10},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["current_stock"] == 90


def test_adjust_stock_unauthorized(client):
    response = client.patch(
        "/skus/SKU001/stock",
        json={"delta": -10},
    )
    assert response.status_code == 403


def test_create_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["reservation_id"]
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "created"
    assert data["expires_at"]


def test_create_reservation_insufficient_stock(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 5},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_idempotent_reservation(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    response1 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res_resp.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"]
    assert data["status"] == "pending"
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 10


def test_confirm_reservation_unauthorized(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res_resp.json()["reservation_id"]

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 403


def test_cancel_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res_resp.json()["reservation_id"]

    response = client.delete(
        f"/reservations/{reservation_id}",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_reservation_unauthorized(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res_resp.json()["reservation_id"]

    response = client.delete(f"/reservations/{reservation_id}")
    assert response.status_code == 403


def test_list_orders_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": api_key},
    )
    reservation_id = res_resp.json()["reservation_id"]
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": api_key},
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["sku_id"] == "SKU001"
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_list_orders_pagination(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )

    for i in range(5):
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 1, "idempotency_key": f"idempotency-{i}"},
            headers={"X-API-Key": api_key},
        )
        reservation_id = res_resp.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    response = client.get("/orders?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    response = client.get("/orders?limit=2&offset=2")
    data = response.json()
    assert len(data["items"]) == 2

    response = client.get("/orders?limit=2&offset=4")
    data = response.json()
    assert len(data["items"]) == 1


def test_list_orders_invalid_limit(client):
    response = client.get("/orders?limit=101")
    assert response.status_code == 422
