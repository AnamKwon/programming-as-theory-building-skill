import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.security import VALID_API_KEY


@pytest.fixture
def client():
    app.dependency_overrides = {}
    repo = Repository(":memory:")
    from commerce_service.app import repo as app_repo

    app_repo.clear_all()
    yield TestClient(app)


@pytest.fixture
def headers():
    return {"X-API-Key": VALID_API_KEY}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client, headers):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
    )
    assert response.status_code == 422


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )

    response = client.post(
        "/skus/SKU001/adjust-stock",
        json={"delta": 20},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 120


def test_adjust_stock_sku_not_found(client, headers):
    response = client.post(
        "/skus/NONEXISTENT/adjust-stock",
        json={"delta": 10},
        headers=headers,
    )
    assert response.status_code == 400


def test_create_reservation_success(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 25,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 25
    assert data["reservation_id"] is not None


def test_create_reservation_insufficient_stock(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 10},
        headers=headers,
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )

    res1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 25,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )
    res2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 25,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )

    assert res1.json()["reservation_id"] == res2.json()["reservation_id"]


def test_confirm_reservation_success(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 25,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "CONFIRMED"
    assert data["confirmed_at"] is not None


def test_confirm_reservation_not_found(client, headers):
    response = client.post(
        "/reservations/NONEXISTENT/confirm",
        json={},
        headers=headers,
    )
    assert response.status_code == 400


def test_confirm_reservation_insufficient_stock(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["reservation_id"]

    client.post(
        "/skus/SKU001/adjust-stock",
        json={"delta": -60},
        headers=headers,
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_cancel_reservation_success(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 100},
        headers=headers,
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 25,
            "idempotency_key": "idempotent-key-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 204


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["orders"]) == 0


def test_list_orders_with_pagination(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "quantity": 1000},
        headers=headers,
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 1,
                "idempotency_key": f"key-{i}",
            },
            headers=headers,
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=headers,
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 25
    assert len(data["orders"]) == 10
    assert data["limit"] == 10
    assert data["offset"] == 0

    response2 = client.get("/orders?limit=10&offset=10")
    assert len(response2.json()["orders"]) == 10

    response3 = client.get("/orders?limit=10&offset=20")
    assert len(response3.json()["orders"]) == 5


def test_unauthorized_mutation_endpoints(client):
    endpoints = [
        ("POST", "/skus"),
        ("POST", "/skus/SKU001/adjust-stock"),
        ("POST", "/reservations"),
        ("POST", "/reservations/res1/confirm"),
        ("POST", "/reservations/res1/cancel"),
    ]

    for method, endpoint in endpoints:
        if method == "POST":
            response = client.post(endpoint, json={})
            assert response.status_code in [401, 403, 422], f"Expected auth error for {endpoint}"
