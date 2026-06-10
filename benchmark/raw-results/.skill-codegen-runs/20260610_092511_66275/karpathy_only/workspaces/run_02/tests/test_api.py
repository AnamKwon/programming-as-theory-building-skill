import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from commerce_service.app import app, get_db
from commerce_service.models import Base

VALID_API_KEY = "test-key-123"


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(db_engine):
    SessionLocal = sessionmaker(bind=db_engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_requires_api_key(client):
    response = client.post("/skus", json={"sku_code": "SKU001", "name": "Product", "quantity": 100})
    assert response.status_code == 401


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU001"
    assert data["quantity"] == 100


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.patch(
        "/skus/1/stock",
        json={"quantity_delta": 25},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 125


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == 1
    assert data["quantity"] == 50
    assert data["state"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 30},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res1 = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "idem-123"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res2 = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "idem-123"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.patch(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert data["state"] == "confirmed"


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.patch(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_cancel_confirmed_reservation_fails(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res_response.json()["id"]

    client.patch(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.patch(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 409


def test_list_orders_with_pagination(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Test Product", "quantity": 1000},
        headers={"X-API-Key": VALID_API_KEY},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = res_response.json()["id"]
        client.patch(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["limit"] == 10
    assert data["offset"] == 0

    response2 = client.get("/orders?limit=10&offset=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 10


def test_unauthorized_mutation_endpoints(client):
    response = client.post("/skus", json={"sku_code": "SKU001", "name": "Product", "quantity": 100})
    assert response.status_code == 401

    response = client.patch("/skus/1/stock", json={"quantity_delta": 10})
    assert response.status_code == 401

    response = client.post("/reservations", json={"sku_id": 1, "quantity": 10})
    assert response.status_code == 401

    response = client.patch("/reservations/1/confirm")
    assert response.status_code == 401

    response = client.patch("/reservations/1/cancel")
    assert response.status_code == 401
