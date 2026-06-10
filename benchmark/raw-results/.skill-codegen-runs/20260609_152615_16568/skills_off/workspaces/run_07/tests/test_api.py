import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, db, service as app_service
from commerce_service.repository import Database


@pytest.fixture
def temp_db_for_app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    db_instance = Database(path)

    app.state.db = db_instance

    yield db_instance

    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def client(temp_db_for_app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(temp_db_for_app):
    from commerce_service.app import app as app_instance
    from commerce_service.app import db as db_instance
    from commerce_service.app import service as service_instance

    app_instance.state.db = temp_db_for_app

    yield


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert "timestamp" in response.json()


def test_create_sku_with_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "WIDGET-001"
    assert response.json()["name"] == "Premium Widget"


def test_create_sku_without_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
    )
    assert response.status_code == 403


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["new_quantity"] == 100


def test_adjust_stock_nonexistent_sku(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 404


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 10
    assert data["status"] == "pending"
    assert data["customer_id"] == "cust_123"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 5},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    first = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert second.status_code == 201
    assert second.json()["id"] == first_id


def test_create_reservation_unauthorized(client):
    response = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
    )
    assert response.status_code == 403


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["order_id"] is not None


def test_confirm_reservation_unauthorized(client):
    response = client.post(
        "/reservations/1/confirm",
        json={},
    )
    assert response.status_code == 403


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 204


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    confirmed = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={},
        headers={"X-API-Key": "test-key-12345"},
    )
    order_id = confirmed.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert len(response.json()["items"]) == 1


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 500},
        headers={"X-API-Key": "test-key-12345"},
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 10,
                "customer_id": "cust_123",
                "idempotency_key": f"key_{i}",
            },
            headers={"X-API-Key": "test-key-12345"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": "test-key-12345"},
        )

    response = client.get("/customers/cust_123/orders?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["page_size"] == 10

    response2 = client.get("/customers/cust_123/orders?page=2&page_size=10")
    assert response2.status_code == 200
    assert len(response2.json()["orders"]) == 5


def test_cleanup_expired_reservations(client):
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "name": "Premium Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 10,
            "customer_id": "cust_123",
            "idempotency_key": "key_1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res.json()["id"]

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    past = (now - timedelta(minutes=20)).isoformat()

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET expires_at = ? WHERE id = ?",
        (past, reservation_id),
    )
    conn.commit()
    conn.close()

    response = client.post(
        "/maintenance/cleanup-expired",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["expired_count"] == 1
