import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, get_db


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["sku_id"] == "SKU-001"


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    response = client.patch(
        "/skus/SKU-001/stock",
        json={"delta": 50},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_adjust_stock_not_found(client):
    response = client.patch(
        "/skus/UNKNOWN/stock",
        json={"delta": 50},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "reserved"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 30},
        headers={"X-API-Key": "dev-key-12345"},
    )
    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/unknown-id/confirm",
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.delete(
        f"/reservations/{reservation_id}",
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200


def test_list_orders_empty(client):
    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0


def test_list_orders_with_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    for i in range(5):
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 10,
                "idempotency_key": f"idem-{i}",
                "ttl_seconds": 3600,
            },
            headers={"X-API-Key": "dev-key-12345"},
        )
        client.post(
            f"/reservations/{res.json()['reservation_id']}/confirm",
            headers={"X-API-Key": "dev-key-12345"},
        )

    response = client.get("/orders?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    response = client.get("/orders?limit=2&offset=2")
    data = response.json()
    assert len(data["items"]) == 2


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
