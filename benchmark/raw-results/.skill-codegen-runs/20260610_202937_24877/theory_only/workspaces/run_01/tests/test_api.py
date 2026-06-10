import pytest
import os
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from commerce_service.app import app, repository, service
from commerce_service.security import API_TOKEN


@pytest.fixture(autouse=True)
def reset_db():
    db_path = "commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    from commerce_service.repository import SQLiteRepository
    test_repo = SQLiteRepository(db_path=db_path)
    yield
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_missing_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": "invalid-token"},
    )
    assert response.status_code == 401


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 20},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 120


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 20
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 10},
        headers={"X-API-Token": API_TOKEN},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["sku"] == data2["sku"]
    assert data1["quantity"] == data2["quantity"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    reservation_id = resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    reservation_id = resp.json()["id"]

    conn = repository._get_connection()
    cursor = conn.cursor()
    old_time = datetime.utcnow() - timedelta(seconds=301)
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_confirm_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    reservation_id = resp.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": API_TOKEN},
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 400


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    resp = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Token": API_TOKEN},
    )
    reservation_id = resp.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Token": API_TOKEN},
    )

    for i in range(15):
        resp = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 1, "idempotency_key": f"idempotency-{i}"},
            headers={"X-API-Token": API_TOKEN},
        )
        reservation_id = resp.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": API_TOKEN},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["size"] == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 15
    assert data["page"] == 2


def test_unauthorized_mutation_endpoints(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 20},
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 20, "idempotency_key": "key"},
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/confirm",
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/cancel",
    )
    assert response.status_code == 401
