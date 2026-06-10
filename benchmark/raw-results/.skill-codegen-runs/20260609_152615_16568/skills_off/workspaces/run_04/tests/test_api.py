import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, get_service
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def client():
    # Override the service to use in-memory database
    repo = Repository()
    service = CommerceService(repo)

    async def override_get_service():
        return service

    app.dependency_overrides[get_service] = override_get_service
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    return "test-key-1"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "PROD-001"
    assert data["id"] is not None


def test_create_sku_missing_api_key(client):
    response = client.post("/skus", json={"name": "PROD-001"})
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": "invalid-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client, api_key):
    # Create SKU first
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Adjust stock
    response = client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 100},
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 100


def test_adjust_stock_requires_api_key(client):
    response = client.post(
        "/stock/1/adjust",
        json={"delta": 100},
    )
    assert response.status_code == 403


def test_create_reservation_success(client, api_key):
    # Setup: create SKU and stock
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 100},
        headers={"x-api-key": api_key},
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reserved"
    assert data["quantity"] == 10


def test_create_reservation_insufficient_stock(client, api_key):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 5},
        headers={"x-api-key": api_key},
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client, api_key):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 100},
        headers={"x-api-key": api_key},
    )

    # Create first reservation
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    data1 = response1.json()

    # Retry with same idempotency key
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    data2 = response2.json()

    assert data1["id"] == data2["id"]


def test_confirm_reservation_success(client, api_key):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 100},
        headers={"x-api-key": api_key},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"


def test_confirm_reservation_requires_api_key(client):
    response = client.post("/reservations/1/confirm")
    assert response.status_code == 403


def test_cancel_reservation_success(client, api_key):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 100},
        headers={"x-api-key": api_key},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
        headers={"x-api-key": api_key},
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"x-api-key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_list_orders_pagination(client, api_key):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"name": "PROD-001"},
        headers={"x-api-key": api_key},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/stock/{sku_id}/adjust",
        json={"delta": 1000},
        headers={"x-api-key": api_key},
    )

    # Create and confirm multiple reservations to generate orders
    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"test-{i}",
                "ttl_seconds": 3600,
            },
            headers={"x-api-key": api_key},
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"x-api-key": api_key},
        )

    # Test first page
    response = client.get("/orders?limit=2&cursor=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["next_cursor"] is not None

    # Test second page
    response2 = client.get(f"/orders?limit=2&cursor={data['next_cursor']}")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 2


def test_list_orders_limit_validation(client):
    response = client.get("/orders?limit=101")
    assert response.status_code == 422  # Validation error


def test_create_reservation_requires_api_key(client):
    response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 10,
            "idempotency_key": "test-1",
            "ttl_seconds": 3600,
        },
    )
    assert response.status_code == 403
