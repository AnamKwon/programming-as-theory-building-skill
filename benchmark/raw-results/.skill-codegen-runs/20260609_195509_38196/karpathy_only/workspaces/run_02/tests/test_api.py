import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import Repository


@pytest.fixture
def client():
    app.dependency_overrides.clear()

    import commerce_service.app as app_module
    original_repo = app_module.repo

    test_repo = Repository("sqlite:///:memory:")
    app_module.repo = test_repo
    app_module.service.repo = test_repo

    yield TestClient(app)

    app_module.repo = original_repo


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_requires_api_key(client):
    response = client.post("/skus", json={"sku_code": "PROD-001", "name": "Product"})
    assert response.status_code == 403


def test_create_sku_with_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_code"] == "PROD-001"
    assert data["available_quantity"] == 0


def test_adjust_stock(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers={"X-API-Key": "dev-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["available_quantity"] == 100


def test_create_reservation_happy_path(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 50},
        headers={"X-API-Key": "dev-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "reserved"


def test_create_reservation_insufficient_stock(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 5},
        headers={"X-API-Key": "dev-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key-123"},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent_retry(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 50},
        headers={"X-API-Key": "dev-key-123"},
    )

    resp1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key-123"},
    )
    order_id_1 = resp1.json()["id"]

    resp2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key-123"},
    )
    order_id_2 = resp2.json()["id"]

    assert order_id_1 == order_id_2


def test_confirm_reservation(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 50},
        headers={"X-API-Key": "dev-key-123"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key-123"},
    )
    order_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{order_id}/confirm",
        headers={"X-API-Key": "dev-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 50},
        headers={"X-API-Key": "dev-key-123"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key-123"},
    )
    order_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{order_id}/cancel",
        headers={"X-API-Key": "dev-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_pagination(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "dev-key-123"},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 500},
        headers={"X-API-Key": "dev-key-123"},
    )

    for i in range(25):
        client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 1, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "dev-key-123"},
        )

    resp1 = client.get("/orders?page=1&per_page=10")
    assert resp1.status_code == 200
    data = resp1.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1

    resp2 = client.get("/orders?page=2&per_page=10")
    assert len(resp2.json()["orders"]) == 10

    resp3 = client.get("/orders?page=3&per_page=10")
    assert len(resp3.json()["orders"]) == 5


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"sku_code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403
