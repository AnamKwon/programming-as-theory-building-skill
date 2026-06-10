import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app
from commerce_service.repository import Base, get_session, Repository

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    def override_get_session():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_session] = override_get_session
    yield session
    app.dependency_overrides.clear()
    session.close()


@pytest.fixture
def client(db_session):
    return TestClient(app)


# Health Check


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# SKU Endpoints


def test_create_sku_success(client):
    response = client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "WIDGET-A"
    assert data["quantity"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
    )
    assert response.status_code == 401


def test_create_sku_duplicate_fails(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 50},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 400


def test_get_sku(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.get("/api/skus/1")
    assert response.status_code == 200
    assert response.json()["name"] == "WIDGET-A"


def test_get_sku_not_found(client):
    response = client.get("/api/skus/999")
    assert response.status_code == 404


# Stock Adjustment


def test_adjust_stock(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.post(
        "/api/stock/1/adjust",
        json={"delta": 50},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 150


def test_adjust_stock_unauthorized(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.post(
        "/api/stock/1/adjust",
        json={"delta": 50},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_sku_not_found(client):
    response = client.post(
        "/api/stock/999/adjust",
        json={"delta": 10},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 404


# Reservation Endpoints


def test_create_reservation_success(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == 1
    assert data["quantity"] == 20
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 200, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["error"]


def test_create_reservation_unauthorized(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_create_reservation_idempotent(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    response1 = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    response2 = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res.json()["id"]
    response = client.post(
        f"/api/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_unauthorized(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res.json()["id"]
    response = client.post(
        f"/api/reservations/{res_id}/confirm",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_confirm_reservation_expired(client, db_session):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res.json()["id"]

    repo = Repository(db_session)
    reservation = repo.get_reservation(res_id)
    reservation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    response = client.post(
        f"/api/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 410


def test_cancel_reservation(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res.json()["id"]
    response = client.post(
        f"/api/reservations/{res_id}/cancel",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_reservation_unauthorized(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 100},
        headers={"X-API-Key": "test-key"},
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": 1, "quantity": 20, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res.json()["id"]
    response = client.post(
        f"/api/reservations/{res_id}/cancel",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


# Order Endpoints


def test_list_orders_empty(client):
    response = client.get("/api/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["orders"] == []


def test_list_orders_pagination(client):
    client.post(
        "/api/skus",
        json={"name": "WIDGET-A", "quantity": 1000},
        headers={"X-API-Key": "test-key"},
    )
    for i in range(5):
        client.post(
            "/api/reservations",
            json={"sku_id": 1, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "test-key"},
        )

    response = client.get("/api/orders?offset=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["orders"]) == 2
    assert data["offset"] == 0
    assert data["limit"] == 2


def test_list_orders_invalid_pagination(client):
    response = client.get("/api/orders?offset=-1&limit=10")
    assert response.status_code == 400

    response = client.get("/api/orders?offset=0&limit=0")
    assert response.status_code == 400

    response = client.get("/api/orders?offset=0&limit=200")
    assert response.status_code == 400


def test_list_orders_reads_dont_require_auth(client):
    response = client.get("/api/orders")
    assert response.status_code == 200
