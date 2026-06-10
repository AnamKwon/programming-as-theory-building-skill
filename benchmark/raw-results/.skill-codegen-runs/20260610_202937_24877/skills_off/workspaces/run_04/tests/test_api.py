import pytest
import os
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from commerce_service.app import app, db, service
from commerce_service.security import STATIC_API_KEY
from commerce_service.repository import Database
from commerce_service.service import InventoryService


@pytest.fixture(scope="function")
def client():
    db_path = "test_api_commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db_instance = Database(db_path)
    service_instance = InventoryService(db_instance)

    import commerce_service.app as app_module
    app_module.db = db_instance
    app_module.service = service_instance

    test_client = TestClient(app)
    yield test_client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def headers():
    return {"X-API-Key": STATIC_API_KEY}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_without_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 403 or response.status_code == 422


def test_create_sku_with_auth(client, headers):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"


def test_adjust_stock(client, headers):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -10},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 90


def test_reserve_insufficient_stock(client, headers):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers=headers
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key1"},
        headers=headers
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_reserve_idempotency(client, headers):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    assert response1.status_code == 201

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_happy_path_workflow(client, headers):
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers
    )
    assert sku_response.status_code == 201

    reserve_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    assert reserve_response.status_code == 201
    reservation_id = reserve_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    assert len(orders_response.json()["items"]) == 1


def test_orders_pagination(client, headers):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers=headers
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
            headers=headers
        )
        client.post(
            f"/reservations/{res.json()['id']}/confirm",
            headers=headers
        )

    page1 = client.get("/orders?page=1&size=10")
    assert page1.status_code == 200
    assert len(page1.json()["items"]) == 10
    assert page1.json()["page"] == 1
    assert page1.json()["total"] == 15

    page2 = client.get("/orders?page=2&size=10")
    assert len(page2.json()["items"]) == 5


def test_expired_reservation(client, headers):
    from commerce_service.repository import Database

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    reservation_id = res.json()["id"]

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    test_db = Database("test_api_commerce.db")
    with test_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE reservations SET created_at = ? WHERE id = ?', (old_time, reservation_id))
        conn.commit()

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers
    )
    assert confirm_response.status_code == 400
    assert "expired" in confirm_response.json()["detail"].lower()


def test_cancel_reservation(client, headers):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers=headers
    )
    reservation_id = res.json()["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"
