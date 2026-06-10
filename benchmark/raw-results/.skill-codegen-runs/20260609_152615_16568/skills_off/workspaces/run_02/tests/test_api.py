import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    os.environ["API_KEY"] = "test-key-123"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
    )
    assert response.status_code == 403


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "SKU001"
    assert data["name"] == "Widget"


def test_list_skus(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.post(
        "/skus",
        json={"id": "SKU002", "name": "Gadget", "price": 19.99},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.get("/skus")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_sku(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.get("/skus/SKU001")
    assert response.status_code == 200
    assert response.json()["id"] == "SKU001"


def test_get_sku_not_found(client):
    response = client.get("/skus/NONEXISTENT")
    assert response.status_code == 404


def test_adjust_stock_unauthorized(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
    )
    assert response.status_code == 403


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["available"] == 100


def test_get_inventory(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.get("/inventory/SKU001")
    assert response.status_code == 200
    assert response.json()["available"] == 100
    assert response.json()["reserved"] == 0


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 10},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 20},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 409


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "pending"
    assert "id" in data
    assert "expires_at" in data

    # Verify inventory was updated
    inv_response = client.get("/inventory/SKU001")
    inv = inv_response.json()
    assert inv["available"] == 90
    assert inv["reserved"] == 10


def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    key = "idempotency-key-123"
    res1 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": key},
        headers={"X-API-Key": "test-key-123"},
    )
    res2 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": key},
        headers={"X-API-Key": "test-key-123"},
    )

    assert res1.json()["id"] == res2.json()["id"]

    # Verify inventory only decremented once
    inv_response = client.get("/inventory/SKU001")
    inv = inv_response.json()
    assert inv["available"] == 90
    assert inv["reserved"] == 10


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    reservation_id = res.json()["id"]

    # Confirm reservation
    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"

    # Verify inventory: reserved should be decremented
    inv_response = client.get("/inventory/SKU001")
    inv = inv_response.json()
    assert inv["available"] == 90
    assert inv["reserved"] == 0

    # Verify order was created
    orders_response = client.get("/orders")
    orders = orders_response.json()
    assert orders["total"] == 1
    assert orders["items"][0]["status"] == "confirmed"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    reservation_id = res.json()["id"]

    # Cancel reservation
    cancel_response = client.delete(
        f"/reservations/{reservation_id}",
        headers={"X-API-Key": "test-key-123"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    # Verify inventory was released
    inv_response = client.get("/inventory/SKU001")
    inv = inv_response.json()
    assert inv["available"] == 100
    assert inv["reserved"] == 0


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    # Create and confirm multiple reservations
    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 1},
            headers={"X-API-Key": "test-key-123"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key-123"},
        )

    # Test pagination
    page1 = client.get("/orders?skip=0&limit=2")
    assert page1.status_code == 200
    data = page1.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["skip"] == 0
    assert data["limit"] == 2

    page2 = client.get("/orders?skip=2&limit=2")
    data = page2.json()
    assert len(data["items"]) == 2

    page3 = client.get("/orders?skip=4&limit=2")
    data = page3.json()
    assert len(data["items"]) == 1


def test_list_orders_invalid_pagination(client):
    response = client.get("/orders?skip=-1&limit=20")
    assert response.status_code == 400

    response = client.get("/orders?skip=0&limit=0")
    assert response.status_code == 400

    response = client.get("/orders?skip=0&limit=200")
    assert response.status_code == 400


def test_get_order(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
        headers={"X-API-Key": "test-key-123"},
    )
    client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"},
    )
    order_id = confirm_res.json()["id"]

    # Get order
    orders = client.get("/orders").json()
    order_id = orders["items"][0]["id"]

    order_response = client.get(f"/orders/{order_id}")
    assert order_response.status_code == 200
    assert order_response.json()["status"] == "confirmed"


def test_unauthorized_endpoints(client):
    # Try to create SKU without API key
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "price": 9.99},
    )
    assert response.status_code == 403

    # Try to adjust stock without API key
    response = client.patch(
        "/inventory/SKU001",
        json={"sku_id": "SKU001", "quantity_change": 100},
    )
    assert response.status_code == 403

    # Try to create reservation without API key
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 10},
    )
    assert response.status_code == 403
