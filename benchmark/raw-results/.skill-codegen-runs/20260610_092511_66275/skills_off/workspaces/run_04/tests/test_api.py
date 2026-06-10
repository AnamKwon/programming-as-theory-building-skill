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
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku(client):
    response = client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    assert response.status_code == 200
    assert response.json()["product_id"] == "SKU001"
    assert response.json()["current_stock"] == 100


def test_adjust_stock(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    response = client.post("/stock/SKU001/adjust", json={"quantity_delta": 50})
    assert response.status_code == 200
    assert response.json()["current_stock"] == 150


def test_adjust_stock_not_found(client):
    response = client.post("/stock/NONEXISTENT/adjust", json={"quantity_delta": 10})
    assert response.status_code == 404


def test_create_reservation_requires_api_key(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    response = client.post(
        "/reservations", json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"}
    )
    assert response.status_code == 403


def test_create_reservation_with_api_key(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    response = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_create_reservation_invalid_api_key(client):
    response = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_create_reservation_insufficient_stock(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 5})
    response = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 409


def test_confirm_reservation(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    res = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm", headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_not_found(client):
    response = client.post("/reservations/NONEXISTENT/confirm", headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 404


def test_cancel_reservation(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    res = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel", headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_requires_api_key(client):
    response = client.get("/orders")
    assert response.status_code == 403


def test_list_orders_with_api_key(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.get("/orders", headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["orders"]) == 1


def test_list_orders_pagination(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    for i in range(15):
        client.post(
            "/reservations",
            json={"product_id": "SKU001", "quantity": 1, "idempotency_key": f"idempotency-{i}"},
            headers={"X-API-Key": "test-key-123"},
        )

    response = client.get("/orders?limit=5&offset=0", headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 200
    assert response.json()["total"] == 15
    assert len(response.json()["orders"]) == 5

    response = client.get("/orders?limit=5&offset=5", headers={"X-API-Key": "test-key-123"})
    assert len(response.json()["orders"]) == 5


def test_get_order_requires_api_key(client):
    response = client.get("/orders/order-123")
    assert response.status_code == 403


def test_get_order_not_found(client):
    response = client.get("/orders/NONEXISTENT", headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 404


def test_get_order(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    res = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    reservation_id = res.json()["id"]

    # Get orders to find the order ID
    orders_res = client.get("/orders", headers={"X-API-Key": "test-key-123"})
    order_id = orders_res.json()["orders"][0]["id"]

    response = client.get(f"/orders/{order_id}", headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 200
    assert response.json()["id"] == order_id
    assert response.json()["product_id"] == "SKU001"


def test_idempotent_reservation_retry(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    res1 = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    res2 = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    assert res1.json()["id"] == res2.json()["id"]
    assert res1.json()["quantity"] == res2.json()["quantity"]


def test_unauthorized_mutation(client):
    client.post("/skus", json={"product_id": "SKU001", "name": "Test Product", "initial_stock": 100})
    response = client.post(
        "/reservations",
        json={"product_id": "SKU001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
