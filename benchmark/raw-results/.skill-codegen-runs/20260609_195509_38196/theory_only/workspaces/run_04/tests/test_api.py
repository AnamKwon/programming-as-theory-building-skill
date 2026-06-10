import pytest

API_KEY = "test-api-key-123"
HEADERS = {"X-API-Key": API_KEY}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client):
    response = client.post(
        "/skus",
        json={"name": "Test SKU", "quantity": 100},
        headers=HEADERS,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test SKU"
    assert data["quantity_available"] == 100
    assert data["id"] == 1


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "Test SKU", "quantity": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "Test SKU", "quantity": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 50},
        headers=HEADERS,
    )
    response = client.post(
        "/skus/1/adjust",
        json={"quantity_delta": 25},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["quantity_available"] == 75


def test_adjust_stock_insufficient(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 50},
        headers=HEADERS,
    )
    response = client.post(
        "/skus/1/adjust",
        json={"quantity_delta": -60},
        headers=HEADERS,
    )
    assert response.status_code == 400


def test_create_reservation(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 100},
        headers=HEADERS,
    )
    response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["quantity"] == 50


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 30},
        headers=HEADERS,
    )
    response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert "Insufficient" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 100},
        headers=HEADERS,
    )
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 100},
        headers=HEADERS,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/999/confirm",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 100},
        headers=HEADERS,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_reservation_confirmed(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 100},
        headers=HEADERS,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers=HEADERS,
    )

    response = client.post(
        f"/reservations/{res_id}/cancel",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 409


def test_get_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["size"] == 10


def test_get_orders_with_confirmed_reservations(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 100},
        headers=HEADERS,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers=HEADERS,
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 50
    assert data["total"] == 1


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"name": "SKU-001", "quantity": 1000},
        headers=HEADERS,
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": 1,
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers=HEADERS,
        )

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 10
    assert data1["total"] == 15
    assert data1["page"] == 1
    assert data1["size"] == 10

    response2 = client.get("/orders?page=2&size=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 5
    assert data2["page"] == 2


def test_get_orders_invalid_pagination(client):
    response = client.get("/orders?page=0&size=10")
    assert response.status_code == 422

    response = client.get("/orders?page=1&size=0")
    assert response.status_code == 422
