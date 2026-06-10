import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.app import app, get_db

API_KEY = "test-api-key-12345"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
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


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "description": "Test", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SKU001"
    assert data["name"] == "Product 1"
    assert data["stock_quantity"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "description": "Test", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "description": "Test", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity_change": 50},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 150


def test_adjust_stock_not_found(client):
    response = client.post(
        "/skus/999/stock",
        json={"quantity_change": 50},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 50},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 409


def test_create_reservation_idempotency(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    idempotency_key = "unique-key-123"
    res1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": idempotency_key},
        headers={"X-API-Key": API_KEY},
    )
    res2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": idempotency_key},
        headers={"X-API-Key": API_KEY},
    )
    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation_success(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product 1", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_empty(client):
    response = client.get(
        "/orders",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_list_orders_pagination(client):
    response = client.get(
        "/orders?page=2&page_size=5",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert data["page_size"] == 5


def test_list_orders_invalid_page(client):
    response = client.get(
        "/orders?page=0",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_list_orders_page_size_too_large(client):
    response = client.get(
        "/orders?page_size=200",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_list_orders_unauthorized(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_create_reservation_unauthorized(client):
    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50},
    )
    assert response.status_code == 401


def test_confirm_reservation_unauthorized(client):
    response = client.post(
        "/reservations/1/confirm",
    )
    assert response.status_code == 401


def test_cancel_reservation_unauthorized(client):
    response = client.post(
        "/reservations/1/cancel",
    )
    assert response.status_code == 401
