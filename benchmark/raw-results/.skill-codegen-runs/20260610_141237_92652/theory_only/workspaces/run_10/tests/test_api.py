import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import commerce_service.repository as repo
from commerce_service.app import app
from commerce_service.repository import Base, get_db


@pytest.fixture
def client():
    # Create test database
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Override the repository's engine and session factory
    original_engine = repo.engine
    original_session_local = repo.SessionLocal

    repo.set_engine(engine, TestingSessionLocal)

    # Also override the get_db dependency
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    # Restore original engine
    repo.set_engine(original_engine, original_session_local)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_no_auth_required(client):
    # Health endpoint should work without API key
    response = client.get("/health")
    assert response.status_code == 200


# SKU Endpoints
def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_without_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert "Invalid API Key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


# Stock Adjustment Endpoints
def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -10},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 90


def test_adjust_stock_without_api_key(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -10},
    )
    assert response.status_code == 401


def test_adjust_stock_sku_not_found(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": -10},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400


# Reservation Endpoints
def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 5},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    # First request
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    res_id1 = response1.json()["id"]

    # Second request with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    res_id2 = response2.json()["id"]

    assert res_id1 == res_id2
    assert response1.json() == response2.json()


def test_create_reservation_without_api_key(client):
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
    )
    assert response.status_code == 401


# Confirmation Endpoints
def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert "id" in data
    assert "created_at" in data


def test_confirm_reservation_without_api_key(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 401


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400


def test_confirm_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    # First confirmation
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )

    # Second confirmation should fail
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400


# Cancellation Endpoints
def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_without_api_key(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel")
    assert response.status_code == 401


def test_cancel_reservation_restores_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"},
    )

    # Verify stock is restored by creating another reservation
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key2"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 201


# Order Listing Endpoints
def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 0


def test_list_orders_with_data(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "key1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["size"] == 10


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": "test-api-key"},
    )

    # Create 25 orders
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key{i}"},
            headers={"X-API-Key": "test-api-key"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-api-key"},
        )

    # Page 1, size 10
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25

    # Page 2, size 10
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 2
    assert data["size"] == 10
    assert data["total"] == 25

    # Page 3, size 10 (last page with 5 items)
    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 3
    assert data["size"] == 10
    assert data["total"] == 25


def test_list_orders_no_auth_required(client):
    response = client.get("/orders")
    assert response.status_code == 200


# Happy path workflow test
def test_happy_path_workflow(client):
    # 1. Create SKU
    sku_response = client.post(
        "/skus",
        json={"sku": "PRODUCT123", "initial_stock": 50},
        headers={"X-API-Key": "test-api-key"},
    )
    assert sku_response.status_code == 201
    assert sku_response.json()["available_stock"] == 50

    # 2. Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT123", "quantity": 5, "idempotency_key": "order-123"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]
    assert res_response.json()["status"] == "PENDING"

    # 3. Confirm reservation
    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    # 4. List orders
    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == order_id
    assert data["items"][0]["reservation_id"] == reservation_id
