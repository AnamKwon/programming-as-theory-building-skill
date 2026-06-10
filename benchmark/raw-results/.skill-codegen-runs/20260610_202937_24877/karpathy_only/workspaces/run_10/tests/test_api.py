import pytest
import os
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import init_db, DATABASE_PATH


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    init_db()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest.fixture
def client():
    return TestClient(app)


VALID_TOKEN = "test-token-123"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100
    assert data["id"] is not None


def test_create_sku_missing_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 401
    assert "Missing API token" in response.json()["detail"]


def test_create_sku_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-token"}
    )
    assert response.status_code == 401
    assert "Invalid API token" in response.json()["detail"]


def test_adjust_stock_success(client):
    # Create SKU first
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["updated_stock"] == 150


def test_adjust_stock_missing_token(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50}
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    # Create SKU with limited stock
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 20},
        headers={"X-API-Key": VALID_TOKEN}
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    # First request
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    data1 = response1.json()

    # Second request with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    data2 = response2.json()

    assert response2.status_code == 201
    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"]


def test_create_reservation_missing_token(client):
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"}
    )
    assert response.status_code == 401


def test_confirm_reservation_success(client):
    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["order_id"] is not None


def test_confirm_reservation_not_pending(client):
    # Create SKU and reservation, then confirm it
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )

    # Try to confirm again
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "not pending" in response.json()["detail"]


def test_confirm_reservation_missing_token(client):
    response = client.post(
        "/reservations/1/confirm"
    )
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    # Create SKU and reservation
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["restored_stock"] == 100


def test_cancel_reservation_not_pending(client):
    # Create SKU and reservation, confirm it
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )

    # Try to cancel
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "not pending" in response.json()["detail"]


def test_cancel_reservation_missing_token(client):
    response = client.post(
        "/reservations/1/cancel"
    )
    assert response.status_code == 401


def test_get_orders_success(client):
    # Create SKU and reservation, confirm it
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 1
    assert len(data["orders"]) == 1


def test_get_orders_pagination(client):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": VALID_TOKEN}
    )

    # Create and confirm 25 reservations
    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": VALID_TOKEN}
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_TOKEN}
        )

    # Test page 1
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25
    assert len(data["orders"]) == 10

    # Test page 2
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["orders"]) == 10

    # Test page 3
    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 3
    assert len(data["orders"]) == 5


def test_happy_path(client):
    # Create SKU
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert sku_response.status_code == 201

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["order_id"]

    # Get orders
    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert orders_data["orders"][0]["id"] == order_id


def test_reservation_expiry(client):
    from datetime import datetime, timezone, timedelta
    from commerce_service.repository import _get_connection

    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_TOKEN}
    )

    # Manually create an expired reservation
    conn = _get_connection()
    cursor = conn.cursor()
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    cursor.execute(
        """INSERT INTO reservations (sku_id, sku, quantity, status, idempotency_key, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, "SKU001", 30, "PENDING", "old-key", old_time)
    )
    conn.commit()
    reservation_id = cursor.lastrowid
    conn.close()

    # Update stock to reflect the reservation
    client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers={"X-API-Key": VALID_TOKEN}
    )

    # Try to confirm
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_TOKEN}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]
