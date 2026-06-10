import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture(autouse=True)
def setup_api_key():
    os.environ["API_KEY"] = "test-api-key"
    yield


@pytest.fixture
def client():
    # Create a fresh in-memory database for each test
    db_url = "sqlite:///:memory:"
    test_repo = Repository(db_url)
    test_service = CommerceService(test_repo)

    # Import app and patch instances
    import commerce_service.app as app_module
    original_repo = app_module.repo
    original_service = app_module.service

    app_module.repo = test_repo
    app_module.service = test_service

    # Create tables
    from commerce_service.models import Base
    Base.metadata.create_all(test_repo.engine)

    client = TestClient(app_module.app)

    yield client, test_repo, test_service

    # Restore original instances
    app_module.repo = original_repo
    app_module.service = original_service


def test_health_check(client):
    client_obj, _, _ = client
    response = client_obj.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_unauthorized(client):
    client_obj, _, _ = client
    response = client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"}
    )
    assert response.status_code == 403


def test_create_sku_authorized(client):
    client_obj, _, _ = client
    response = client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["sku_code"] == "SKU001"


def test_adjust_stock_not_found(client):
    client_obj, _, _ = client
    response = client_obj.post(
        "/stock/999/adjust",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 404


def test_adjust_stock_success(client):
    client_obj, _, _ = client
    # Create SKU first
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    # Adjust stock
    response = client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["available"] == 100.0


def test_create_reservation_success(client):
    client_obj, _, _ = client
    # Setup
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    # Create reservation
    response = client_obj.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client_obj, _, _ = client
    # Setup with only 50 stock
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 50},
        headers={"X-API-Key": "test-api-key"}
    )
    # Try to reserve 100
    response = client_obj.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 100, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    client_obj, _, _ = client
    # Setup
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    # First request
    response1 = client_obj.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-api-key"}
    )
    res_id = response1.json()["id"]

    # Second request with same key but different quantity
    response2 = client_obj.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-api-key"}
    )
    # Should return same reservation with original quantity
    assert response2.json()["id"] == res_id
    assert float(response2.json()["quantity"]) == 30.0


def test_confirm_reservation_success(client):
    client_obj, _, _ = client
    # Setup and create reservation
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    res_resp = client_obj.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-api-key"}
    )
    res_id = res_resp.json()["id"]

    # Confirm
    response = client_obj.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"


def test_cancel_reservation_success(client):
    client_obj, _, _ = client
    # Setup and create reservation
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    res_resp = client_obj.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-api-key"}
    )
    res_id = res_resp.json()["id"]

    # Cancel
    response = client_obj.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_list_orders_unauthorized(client):
    client_obj, _, _ = client
    response = client_obj.get("/orders")
    assert response.status_code == 403


def test_list_orders_pagination(client):
    client_obj, _, _ = client
    # Setup
    client_obj.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product"},
        headers={"X-API-Key": "test-api-key"}
    )
    client_obj.post(
        "/stock/1/adjust",
        json={"adjustment": 1000},
        headers={"X-API-Key": "test-api-key"}
    )

    # Create and confirm 15 orders
    for i in range(15):
        res_resp = client_obj.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "test-api-key"}
        )
        res_id = res_resp.json()["id"]
        client_obj.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-api-key"}
        )

    # Test first page
    response = client_obj.get(
        "/orders?limit=10&offset=0",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10

    # Test second page
    response = client_obj.get(
        "/orders?limit=10&offset=10",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
