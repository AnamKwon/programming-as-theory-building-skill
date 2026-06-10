import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.commerce_service.models import Base, ReservationModel
from src.commerce_service.app import app, get_db

API_KEY = "test-api-key-12345"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_with_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["stock"] == 100


def test_create_sku_without_auth(client):
    response = client.post(
        "/skus", json={"sku": "SKU-001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock(client):
    # Create SKU first
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Adjust stock positive
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 20},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 120

    # Adjust stock negative
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -30},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 90


def test_adjust_stock_without_auth(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 20},
    )
    assert response.status_code == 401


def test_reserve_stock_success(client):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Reserve stock
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 20
    assert data["status"] == "PENDING"
    assert "id" in data
    assert "created_at" in data


def test_reserve_stock_insufficient(client):
    # Create SKU with small stock
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 10},
        headers={"X-API-Key": API_KEY},
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_reserve_stock_idempotency(client):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # First reservation
    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    id1 = response1.json()["id"]

    # Second with same key
    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    id2 = response2.json()["id"]

    assert id1 == id2
    assert response2.status_code == 201


def test_reserve_stock_without_auth(client):
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
    )
    assert response.status_code == 401


def test_confirm_reservation(client):
    # Setup
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res.json()["id"]

    # Confirm
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "created_at" in data


def test_confirm_reservation_without_auth(client):
    response = client.post(
        "/reservations/1/confirm",
    )
    assert response.status_code == 401


def test_confirm_non_pending_reservation(client):
    # Setup
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res.json()["id"]

    # Confirm once
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    # Try to confirm again
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_cancel_reservation(client):
    # Setup
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res.json()["id"]

    # Cancel
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_without_auth(client):
    response = client.post(
        "/reservations/1/cancel",
    )
    assert response.status_code == 401


def test_cancel_non_pending_reservation(client):
    # Setup
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 20,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res.json()["id"]

    # Confirm
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    # Try to cancel
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_get_orders(client):
    # Setup
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create and confirm multiple orders
    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idempotency-{i}",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    # Get page 1
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["total"] == 15

    # Get page 2
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2
    assert data["total"] == 15


def test_get_orders_default_pagination(client):
    # Setup
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create and confirm 5 orders
    for i in range(5):
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idempotency-{i}",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    # Get with default pagination
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 5
