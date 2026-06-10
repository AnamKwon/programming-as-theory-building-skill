import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app, repo
from datetime import datetime


@pytest.fixture(autouse=True)
def reset_db():
    repo.clear_db()
    yield
    repo.clear_db()


@pytest.fixture
def client():
    return TestClient(app)


VALID_TOKEN = "test-token-12345"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["stock"] == 100


def test_create_sku_missing_token(client):
    response = client.post(
        "/skus", json={"sku": "WIDGET-001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": "wrong-token"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 25},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_stock"] == 125


def test_adjust_stock_missing_token(client):
    response = client.post(
        "/stock/adjust", json={"sku": "WIDGET-001", "amount": 25}
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 25
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 20},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_missing_token(client):
    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
    )
    assert response.status_code == 401


def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    reservation_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 25
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_expired(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    reservation_id = res_resp.json()["id"]

    past_time = (datetime.utcnow().timestamp() - 310)
    conn = repo._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (datetime.fromtimestamp(past_time).isoformat(), reservation_id),
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]


def test_confirm_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    reservation_id = res_resp.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400


def test_confirm_reservation_missing_token(client):
    response = client.post("/reservations/1/confirm")
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    reservation_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_resp = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 25, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    reservation_id = res_resp.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400


def test_cancel_reservation_missing_token(client):
    response = client.post("/reservations/1/cancel")
    assert response.status_code == 401


def test_get_orders_success(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 1000},
        headers={"X-API-Token": VALID_TOKEN},
    )

    for i in range(5):
        res_resp = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers={"X-API-Token": VALID_TOKEN},
        )
        reservation_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": VALID_TOKEN},
        )

    response = client.get(
        "/orders?page=1&size=10", headers={"X-API-Token": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 5


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 5000},
        headers={"X-API-Token": VALID_TOKEN},
    )

    for i in range(25):
        res_resp = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers={"X-API-Token": VALID_TOKEN},
        )
        reservation_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": VALID_TOKEN},
        )

    response1 = client.get(
        "/orders?page=1&size=10", headers={"X-API-Token": VALID_TOKEN}
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["total"] == 25

    response2 = client.get(
        "/orders?page=2&size=10", headers={"X-API-Token": VALID_TOKEN}
    )
    data2 = response2.json()
    assert len(data2["orders"]) == 10

    response3 = client.get(
        "/orders?page=3&size=10", headers={"X-API-Token": VALID_TOKEN}
    )
    data3 = response3.json()
    assert len(data3["orders"]) == 5
    assert data3["total"] == 25


def test_get_orders_missing_token(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_workflow(client):
    sku_resp = client.post(
        "/skus",
        json={"sku": "GADGET-100", "initial_stock": 50},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert sku_resp.status_code == 201

    res_resp = client.post(
        "/reservations",
        json={"sku": "GADGET-100", "quantity": 15, "idempotency_key": "order-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert res_resp.status_code == 201
    reservation_id = res_resp.json()["id"]

    order_resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert order_resp.status_code == 200
    order_id = order_resp.json()["id"]

    orders_resp = client.get(
        "/orders?page=1&size=10", headers={"X-API-Token": VALID_TOKEN}
    )
    assert orders_resp.status_code == 200
    orders = orders_resp.json()
    assert len(orders["orders"]) == 1
    assert orders["orders"][0]["id"] == order_id
    assert orders["orders"][0]["sku"] == "GADGET-100"
    assert orders["orders"][0]["quantity"] == 15
