import pytest
import os
import tempfile
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base

VALID_API_KEY = "test-key-1"


@pytest.fixture
def db_file():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def db(db_file):
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_file):
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    engine.dispose()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "PROD-001"
    assert data["stock"] == 100
    assert data["available"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post("/skus", json={"sku": "PROD-001", "stock": 100})
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_get_sku(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.get("/skus/1")
    assert response.status_code == 200
    assert response.json()["sku"] == "PROD-001"


def test_get_sku_not_found(client):
    response = client.get("/skus/999")
    assert response.status_code == 404


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.patch(
        "/skus/1/stock",
        json={"delta": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 150


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 10
    assert data["status"] == "pending"
    assert data["order_id"] is not None


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 10},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response1 = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]
    assert response1.json()["order_id"] == response2.json()["order_id"]

    # Verify stock was allocated once
    sku = client.get("/skus/1").json()
    assert sku["reserved"] == 10
    assert sku["available"] == 90


def test_get_reservation(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res.json()["id"]
    response = client.get(f"/reservations/{res_id}")
    assert response.status_code == 200
    assert response.json()["quantity"] == 10


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res.json()["id"]
    response = client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res.json()["id"]
    response = client.post(
        f"/reservations/{res_id}/cancel",
        json={},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Verify stock was released
    sku = client.get("/skus/1").json()
    assert sku["reserved"] == 0
    assert sku["available"] == 100


def test_cancel_confirmed_reservation_fails(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res.json()["id"]
    client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        f"/reservations/{res_id}/cancel",
        json={},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert "immutable" in response.json()["detail"]


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    order_id = res.json()["order_id"]
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["order_id"] == order_id


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 1000},
        headers={"X-API-Key": VALID_API_KEY},
    )
    # Create and confirm multiple orders
    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 1, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": VALID_API_KEY},
        )

    # Test first page
    response = client.get("/orders?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total"] == 15
    assert data["total_pages"] == 2

    # Test second page
    response = client.get("/orders?page=2&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2


def test_unauthorized_reservation_mutation(client):
    client.post(
        "/skus",
        json={"sku": "PROD-001", "stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "key-1"},
    )
    assert response.status_code == 401
