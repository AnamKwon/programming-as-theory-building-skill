import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app, repo, service
from src.commerce_service.repository import Repository

# Override repo and service with in-memory database for tests
@pytest.fixture(autouse=True)
def setup_test_db():
    test_repo = Repository("sqlite:///:memory:")
    test_service = service.__class__(test_repo)

    app.dependency_overrides[repo] = lambda: test_repo
    app.dependency_overrides[service] = lambda: test_service

    yield test_service

    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def headers():
    return {"X-API-Key": "test-key-123"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
    )
    assert response.status_code == 403


def test_create_sku_authorized(client, headers):
    response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "PROD-001"
    assert data["name"] == "Test Product"
    assert data["id"] is not None


def test_adjust_stock(client, headers):
    # Create SKU first
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    # Adjust stock
    response = client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=headers,
    )
    assert response.status_code == 204


def test_adjust_stock_sku_not_found(client, headers):
    response = client.post(
        "/stock/adjust",
        json={"sku_id": 999, "quantity_delta": 100},
        headers=headers,
    )
    assert response.status_code == 404


def test_create_reservation(client, headers):
    # Setup: Create SKU and add stock
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=headers,
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-123",
            "reservation_ttl_seconds": 300,
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client, headers):
    # Setup: Create SKU with insufficient stock
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 5},
        headers=headers,
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-123",
        },
        headers=headers,
    )
    assert response.status_code == 409


def test_reservation_idempotency(client, headers):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=headers,
    )

    # Create reservation
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-123",
        },
        headers=headers,
    )
    assert response1.status_code == 201
    id1 = response1.json()["id"]

    # Retry with same key
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-123",
        },
        headers=headers,
    )
    assert response2.status_code == 201
    id2 = response2.json()["id"]

    assert id1 == id2


def test_confirm_reservation(client, headers):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=headers,
    )

    reservation_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-123",
        },
        headers=headers,
    )
    reservation_id = reservation_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert data["status"] == "confirmed"


def test_cancel_reservation(client, headers):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=headers,
    )

    reservation_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-123",
        },
        headers=headers,
    )
    reservation_id = reservation_response.json()["id"]

    # Cancel reservation
    response = client.delete(
        f"/reservations/{reservation_id}",
        headers=headers,
    )
    assert response.status_code == 204


def test_cancel_non_existent_reservation(client, headers):
    response = client.delete(
        "/reservations/999",
        headers=headers,
    )
    assert response.status_code == 404


def test_list_orders_pagination(client, headers):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=headers,
    )

    # Create and confirm multiple orders
    for i in range(15):
        reservation_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 1,
                "idempotency_key": f"key-{i}",
            },
            headers=headers,
        )
        reservation_id = reservation_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers,
        )

    # Test first page
    response = client.get("/orders?offset=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["offset"] == 0
    assert data["limit"] == 10

    # Test second page
    response = client.get("/orders?offset=10&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 15


def test_list_orders_default_pagination(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["offset"] == 0
    assert data["limit"] == 10


def test_unauthorized_mutation_endpoints(client):
    # Test POST /skus without API key
    response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
    )
    assert response.status_code == 403

    # Test POST /stock/adjust without API key
    response = client.post(
        "/stock/adjust",
        json={"sku_id": 1, "quantity_delta": 100},
    )
    assert response.status_code == 403

    # Test POST /reservations without API key
    response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 10,
            "idempotency_key": "key-123",
        },
    )
    assert response.status_code == 403


def test_unauthorized_with_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "PROD-001", "name": "Test Product"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403
