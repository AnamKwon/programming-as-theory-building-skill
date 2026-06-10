import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Repository


API_KEY = "test-key"


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["current_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 403


def test_get_sku(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    response = client.get("/skus/SKU-001")
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["available_stock"] == 100


def test_get_nonexistent_sku(client):
    response = client.get("/skus/SKU-999")
    assert response.status_code == 404


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    response = client.post(
        "/skus/SKU-001/adjust-stock",
        json={"delta": 10},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current_stock"] == 110


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 50},
        headers={"x-api-key": API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 100, "idempotency_key": "key-1"},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    response1 = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"


def test_confirm_reservation_missing_api_key(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(f"/reservations/{res_id}/confirm")
    assert response.status_code == 401


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    res_id = res_response.json()["reservation_id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"x-api-key": API_KEY},
    )
    order_id = confirm_response.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == order_id
    assert len(data["reservations"]) == 1


def test_list_orders_requires_api_key(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 1000},
        headers={"x-api-key": API_KEY},
    )

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
        )
        res_id = res_response.json()["reservation_id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": API_KEY},
        )

    response1 = client.get(
        "/orders?skip=0&limit=3",
        headers={"x-api-key": API_KEY},
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 3
    assert data1["total"] == 5
    assert data1["skip"] == 0
    assert data1["limit"] == 3

    response2 = client.get(
        "/orders?skip=3&limit=3",
        headers={"x-api-key": API_KEY},
    )
    data2 = response2.json()
    assert len(data2["items"]) == 2


def test_request_validation_errors(client):
    response = client.post(
        "/skus",
        json={"sku_id": "", "name": "Widget A", "initial_stock": 100},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 422

    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": -5},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 422


def test_negative_stock_prevented(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A", "initial_stock": 50},
        headers={"x-api-key": API_KEY},
    )
    response = client.post(
        "/skus/SKU-001/adjust-stock",
        json={"delta": -100},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current_stock"] == 0
