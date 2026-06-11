import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import os

os.environ["DB_PATH"] = ":memory:"

from commerce_service.app import app, repo, service
from commerce_service.security import VALID_API_KEY


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": VALID_API_KEY}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, auth_headers):
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU", "amount": 50},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_missing_api_key(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU", "amount": 50},
    )
    assert response.status_code == 401


def test_create_reservation_success(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 30},
        headers=auth_headers,
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    response1 = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"]

    sku_data = repo.get_sku_by_name("TEST-SKU")
    assert sku_data["available_stock"] == 50


def test_create_reservation_missing_api_key(client):
    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
    )
    assert response.status_code == 401


def test_confirm_reservation_success(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert "order_id" in data


def test_confirm_reservation_expired(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    reservation_id = res.json()["id"]

    old_time = (datetime.utcnow() - timedelta(seconds=310)).isoformat()
    cursor = repo._get_connection().cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id)
    )
    cursor.connection.commit()
    cursor.connection.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()

    sku_data = repo.get_sku_by_name("TEST-SKU")
    assert sku_data["available_stock"] == 100


def test_confirm_reservation_missing_api_key(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 401


def test_cancel_reservation_success(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert data["status"] == "CANCELLED"

    sku_data = repo.get_sku_by_name("TEST-SKU")
    assert sku_data["available_stock"] == 100


def test_cancel_reservation_missing_api_key(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    reservation_id = res.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel")
    assert response.status_code == 401


def test_list_orders_pagination(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 500},
        headers=auth_headers,
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={
                "sku": "TEST-SKU",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers=auth_headers,
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )

    response1 = client.get("/orders?page=1&size=10", headers=auth_headers)
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["total"] == 25
    assert data1["page"] == 1
    assert data1["size"] == 10

    response2 = client.get("/orders?page=2&size=10", headers=auth_headers)
    data2 = response2.json()
    assert len(data2["orders"]) == 10

    response3 = client.get("/orders?page=3&size=10", headers=auth_headers)
    data3 = response3.json()
    assert len(data3["orders"]) == 5


def test_list_orders_missing_api_key(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_workflow(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU", "initial_stock": 100},
        headers=auth_headers,
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers,
    )
    assert confirm_res.status_code == 200

    orders_res = client.get("/orders?page=1&size=10", headers=auth_headers)
    assert orders_res.status_code == 200
    orders_data = orders_res.json()
    assert len(orders_data["orders"]) == 1
    assert orders_data["orders"][0]["reservation_id"] == reservation_id
