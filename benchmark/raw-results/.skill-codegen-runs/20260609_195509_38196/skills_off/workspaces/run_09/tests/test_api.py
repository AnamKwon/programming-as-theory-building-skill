import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base

DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session():
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def api_key():
    return "test-api-key-123"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_without_api_key(client):
    response = client.post("/skus", json={"sku_code": "SKU001", "initial_stock": 100})
    assert response.status_code == 401


def test_create_sku_with_api_key(client, api_key):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_code"] == "SKU001"
    assert data["current_stock"] == 100
    assert data["reserved_count"] == 0


def test_create_duplicate_sku_fails(client, api_key):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 400


def test_adjust_stock(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/stock",
        json={"adjustment": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["current_stock"] == 150


def test_adjust_stock_nonexistent_sku(client, api_key):
    response = client.post(
        "/skus/999/stock",
        json={"adjustment": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_reserve_inventory_happy_path(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "order-123",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 30
    assert data["status"] == "pending"


def test_reserve_inventory_insufficient_stock(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 150,
            "idempotency_key": "order-123",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409


def test_reserve_inventory_idempotent_retry(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # First reservation
    res1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "order-123",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": api_key},
    )
    res1_data = res1.json()

    # Retry with same idempotency key
    res2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "order-123",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": api_key},
    )
    res2_data = res2.json()

    # Should return same reservation
    assert res1_data["id"] == res2_data["id"]


def test_confirm_reservation_happy_path(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "order-123",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert confirm_response.status_code == 200
    data = confirm_response.json()
    assert data["reservation"]["status"] == "confirmed"
    assert data["order"]["status"] == "confirmed"


def test_confirm_nonexistent_reservation(client, api_key):
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_cancel_reservation_happy_path(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 30,
            "idempotency_key": "order-123",
            "ttl_seconds": 300,
        },
        headers={"X-API-Key": api_key},
    )
    res_id = res_response.json()["id"]

    cancel_response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_cancel_nonexistent_reservation(client, api_key):
    response = client.post(
        "/reservations/999/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_list_orders_pagination(client, api_key):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": api_key},
    )
    sku_id = sku_response.json()["id"]

    # Create and confirm 5 orders
    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"order-{i}",
                "ttl_seconds": 300,
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    # Test pagination
    response = client.get("/orders?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["orders"]) == 2

    response = client.get("/orders?skip=2&limit=2")
    data = response.json()
    assert len(data["orders"]) == 2

    response = client.get("/orders?skip=4&limit=2")
    data = response.json()
    assert len(data["orders"]) == 1


def test_unauthorized_mutation(client):
    response = client.post("/skus", json={"sku_code": "SKU001", "initial_stock": 100})
    assert response.status_code == 401


def test_list_orders_no_auth_required(client):
    response = client.get("/orders")
    assert response.status_code == 200
