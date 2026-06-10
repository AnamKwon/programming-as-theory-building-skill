import pytest
import tempfile
from fastapi.testclient import TestClient

from commerce_service.app import app, repo, service
from commerce_service.repository import Repository
from commerce_service.security import API_KEY


@pytest.fixture(autouse=True)
def setup_test_db():
    """Replace repo and service with test instances before each test."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        db_path = f.name

    test_repo = Repository(db_path=db_path)
    app.dependency_overrides = {}
    yield test_repo


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_success(client, auth_headers):
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Widget"
    assert data["quantity"] == 100
    assert data["id"] > 0


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"name": "Widget", "quantity": 100}
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        headers={"X-API-Key": "wrong-key"},
        json={"name": "Widget", "quantity": 100}
    )
    assert response.status_code == 403


def test_get_sku_success(client, auth_headers):
    # Create a SKU
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    # Retrieve it
    response = client.get(f"/skus/{sku_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sku_id
    assert data["name"] == "Widget"


def test_get_sku_not_found(client):
    response = client.get("/skus/999")
    assert response.status_code == 404


def test_adjust_stock_success(client, auth_headers):
    # Create a SKU
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    # Adjust stock
    response = client.post(
        f"/skus/{sku_id}/adjust",
        headers=auth_headers,
        json={"adjustment": 50}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 150


def test_adjust_stock_insufficient(client, auth_headers):
    # Create a SKU
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    # Try to reduce beyond available
    response = client.post(
        f"/skus/{sku_id}/adjust",
        headers=auth_headers,
        json={"adjustment": -150}
    )
    assert response.status_code == 400


def test_create_reservation_success(client, auth_headers):
    # Create a SKU
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    # Create reservation
    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 30
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client, auth_headers):
    # Create a SKU with limited stock
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 20}
    )
    sku_id = response.json()["id"]

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    assert response.status_code == 409


def test_create_reservation_duplicate_idempotency_key(client, auth_headers):
    # Create a SKU
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    # Create first reservation
    client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )

    # Try to create another with same idempotency key
    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    assert response.status_code == 409


def test_get_reservation(client, auth_headers):
    # Create a SKU and reservation
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    reservation_id = response.json()["id"]

    # Retrieve it
    response = client.get(f"/reservations/{reservation_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == reservation_id


def test_confirm_reservation_success(client, auth_headers):
    # Create a SKU and reservation
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    reservation_id = response.json()["id"]

    # Confirm it
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert len(data["items"]) == 1


def test_cancel_reservation_success(client, auth_headers):
    # Create a SKU and reservation
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    reservation_id = response.json()["id"]

    # Check stock is deducted
    response = client.get(f"/skus/{sku_id}")
    assert response.json()["quantity"] == 70

    # Cancel it
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"

    # Check stock is restored
    response = client.get(f"/skus/{sku_id}")
    assert response.json()["quantity"] == 100


def test_list_orders_pagination(client, auth_headers):
    # Create a SKU
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 1000}
    )
    sku_id = response.json()["id"]

    # Create and confirm multiple reservations
    for i in range(25):
        response = client.post(
            "/reservations",
            headers=auth_headers,
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "expires_in_seconds": 3600,
                "idempotency_key": f"key-{i}"
            }
        )
        reservation_id = response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers
        )

    # Test pagination
    response = client.get("/orders?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["skip"] == 0
    assert data["limit"] == 10

    response = client.get("/orders?skip=10&limit=10")
    assert len(response.json()["orders"]) == 10

    response = client.get("/orders?skip=20&limit=10")
    assert len(response.json()["orders"]) == 5


def test_unauthorized_mutations(client):
    # Try to create SKU without API key
    response = client.post(
        "/skus",
        json={"name": "Widget", "quantity": 100}
    )
    assert response.status_code == 403

    # Try to adjust stock without API key
    response = client.post(
        "/skus/1/adjust",
        json={"adjustment": 10}
    )
    assert response.status_code == 403

    # Try to create reservation without API key
    response = client.post(
        "/reservations",
        json={
            "sku_id": 1,
            "quantity": 10,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    assert response.status_code == 403

    # Try to confirm reservation without API key
    response = client.post(
        "/reservations/1/confirm"
    )
    assert response.status_code == 403

    # Try to cancel reservation without API key
    response = client.post(
        "/reservations/1/cancel"
    )
    assert response.status_code == 403


def test_get_order(client, auth_headers):
    # Create a SKU and reservation
    response = client.post(
        "/skus",
        headers=auth_headers,
        json={"name": "Widget", "quantity": 100}
    )
    sku_id = response.json()["id"]

    response = client.post(
        "/reservations",
        headers=auth_headers,
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "expires_in_seconds": 3600,
            "idempotency_key": "key-1"
        }
    )
    reservation_id = response.json()["id"]

    # Confirm to create order
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers
    )
    order_id = response.json()["id"]

    # Retrieve the order
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["status"] == "completed"
