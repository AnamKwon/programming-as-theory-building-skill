import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from commerce_service.app import app, db, service


@pytest.fixture(autouse=True)
def setup():
    db._init_schema()
    yield
    db.conn.execute("DELETE FROM orders")
    db.conn.execute("DELETE FROM reservations")
    db.conn.execute("DELETE FROM skus")
    db.conn.commit()


@pytest.fixture
def client():
    return TestClient(app)


VALID_API_KEY = "test-api-key-12345"


def test_health_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_no_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 25},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 125


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 5},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 25
    assert data["status"] == "PENDING"


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response1.status_code == 201
    res1_id = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response2.status_code == 200
    assert response2.json()["id"] == res1_id

    sku_check = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert sku_check.json()["available_stock"] == 75


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == res_id
    assert "created_at" in data


def test_confirm_reservation_expired(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_id = res_response.json()["id"]

    db.conn.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        ((datetime.utcnow() - timedelta(seconds=301)).isoformat(), res_id)
    )
    db.conn.commit()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()

    sku_check = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert sku_check.json()["available_stock"] == 100


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 25, "idempotency_key": "idem-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    sku_check = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert sku_check.json()["available_stock"] == 100


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"idem-{i}"},
            headers={"X-API-Key": VALID_API_KEY}
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY}
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25
    assert len(data["items"]) == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10

    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU-PRODUCT", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-PRODUCT", "quantity": 10, "idempotency_key": "order-123"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert res.status_code == 201
    res_id = res.json()["id"]

    confirm = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert confirm.status_code == 200
    order_data = confirm.json()

    orders = client.get("/orders")
    assert orders.status_code == 200
    assert len(orders.json()["items"]) == 1
    assert orders.json()["items"][0]["id"] == order_data["id"]
