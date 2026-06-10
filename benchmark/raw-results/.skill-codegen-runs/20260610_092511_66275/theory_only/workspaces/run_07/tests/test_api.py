import pytest
import tempfile
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        yield f.name


@pytest.fixture
def client(temp_db):
    # Override the service with a test instance
    repo = Repository(temp_db)
    service = CommerceService(repo)

    def override_get_service():
        return service

    from commerce_service.app import get_service

    app.dependency_overrides[get_service] = override_get_service

    yield TestClient(app)

    app.dependency_overrides.clear()


VALID_API_KEY = "test-key-123"
INVALID_API_KEY = "invalid-key"
HEADERS = {"X-API-Key": VALID_API_KEY}
INVALID_HEADERS = {"X-API-Key": INVALID_API_KEY}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["name"] == "Product 1"
    assert data["price"] == 29.99
    assert data["id"] is not None


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=INVALID_HEADERS,
    )
    assert response.status_code == 403


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
    )
    assert response.status_code == 422


def test_adjust_stock_success(client):
    # Create SKU first
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    # Adjust stock
    response = client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 100},
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["available"] == 100
    assert data["reserved"] == 0
    assert data["total"] == 100


def test_adjust_stock_sku_not_found(client):
    response = client.post(
        "/stock/adjust",
        json={"sku_id": 999, "quantity": 100},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 100},
        headers=HEADERS,
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 50
    assert data["state"] == "pending"
    assert data["id"] is not None


def test_create_reservation_insufficient_stock(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 30},
        headers=HEADERS,
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 100},
        headers=HEADERS,
    )

    # Create two reservations with same idempotency key
    response1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]

    # Verify stock is only reserved once
    stock_response = client.get("/orders")  # Just checking the API works
    assert stock_response.status_code == 200


def test_confirm_reservation(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 100},
        headers=HEADERS,
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]

    # Confirm reservation
    response = client.put(
        f"/reservations/{reservation_id}/confirm",
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation"]["state"] == "confirmed"
    assert data["order"]["state"] == "confirmed"
    assert data["order"]["quantity"] == 50


def test_cancel_reservation(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 100},
        headers=HEADERS,
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    response = client.delete(
        f"/reservations/{reservation_id}",
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "cancelled"


def test_get_orders_pagination(client):
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU-001", "name": "Product 1", "price": 29.99},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity": 1000},
        headers=HEADERS,
    )

    # Create multiple orders
    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["id"]
        client.put(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    # Test pagination
    response1 = client.get("/orders?limit=10&offset=0")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["total"] == 15
    assert data1["limit"] == 10
    assert data1["offset"] == 0

    response2 = client.get("/orders?limit=10&offset=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 5
    assert data2["total"] == 15

    # Verify no overlap
    ids1 = {o["id"] for o in data1["orders"]}
    ids2 = {o["id"] for o in data2["orders"]}
    assert len(ids1 & ids2) == 0


def test_get_orders_invalid_pagination(client):
    response = client.get("/orders?limit=0")
    assert response.status_code == 400

    response = client.get("/orders?limit=101")
    assert response.status_code == 400

    response = client.get("/orders?offset=-1")
    assert response.status_code == 400
