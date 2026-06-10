"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


API_KEY = "secret-key"


def get_headers(authenticated=True):
    if authenticated:
        return {"X-API-Key": API_KEY}
    return {}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "SKU001"
    assert data["name"] == "Test Product"
    assert data["stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(authenticated=False),
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_create_sku_conflict(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    response = client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Another", "stock": 50},
        headers=get_headers(),
    )
    assert response.status_code == 409


def test_adjust_stock_success(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    response = client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU001", "delta": 20},
        headers=get_headers(),
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 120


def test_adjust_stock_negative_conflict(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 50},
        headers=get_headers(),
    )
    response = client.post(
        "/api/stock/adjust",
        json={"sku_id": "SKU001", "delta": -60},
        headers=get_headers(),
    )
    assert response.status_code == 409


def test_adjust_stock_not_found(client):
    response = client.post(
        "/api/stock/adjust",
        json={"sku_id": "NONEXISTENT", "delta": 10},
        headers=get_headers(),
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    response = client.post(
        "/api/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "res-1"},
        headers=get_headers(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"
    assert "id" in data


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 50},
        headers=get_headers(),
    )
    response = client.post(
        "/api/reservations",
        json={"sku_id": "SKU001", "quantity": 60, "idempotency_key": "res-1"},
        headers=get_headers(),
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    res1 = client.post(
        "/api/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "res-1"},
        headers=get_headers(),
    ).json()

    res2 = client.post(
        "/api/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "res-1"},
        headers=get_headers(),
    ).json()

    assert res1["id"] == res2["id"]


def test_confirm_reservation_success(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "res-1"},
        headers=get_headers(),
    ).json()

    response = client.post(
        f"/api/reservations/{res['id']}/confirm",
        headers=get_headers(),
    )
    assert response.status_code == 200
    order = response.json()
    assert order["sku_id"] == "SKU001"
    assert order["quantity"] == 30

    sku = client.post(
        "/api/skus",
        json={"id": "SKU002", "name": "Check", "stock": 0},
        headers=get_headers(),
    ).json()


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/api/reservations/NONEXISTENT/confirm",
        headers=get_headers(),
    )
    assert response.status_code == 404


def test_confirm_reservation_unauthorized(client):
    response = client.post(
        "/api/reservations/SOMEID/confirm",
        headers=get_headers(authenticated=False),
    )
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )
    res = client.post(
        "/api/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "res-1"},
        headers=get_headers(),
    ).json()

    response = client.post(
        f"/api/reservations/{res['id']}/cancel",
        headers=get_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_not_found(client):
    response = client.post(
        "/api/reservations/NONEXISTENT/cancel",
        headers=get_headers(),
    )
    assert response.status_code == 404


def test_list_orders_success(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )

    for i in range(5):
        res = client.post(
            "/api/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": f"res-{i}"},
            headers=get_headers(),
        ).json()
        client.post(
            f"/api/reservations/{res['id']}/confirm",
            headers=get_headers(),
        )

    response = client.get("/api/orders?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_list_orders_pagination(client):
    client.post(
        "/api/skus",
        json={"id": "SKU001", "name": "Test Product", "stock": 100},
        headers=get_headers(),
    )

    for i in range(5):
        res = client.post(
            "/api/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": f"res-{i}"},
            headers=get_headers(),
        ).json()
        client.post(
            f"/api/reservations/{res['id']}/confirm",
            headers=get_headers(),
        )

    response = client.get("/api/orders?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["page"] == 2


def test_list_orders_invalid_page_size(client):
    response = client.get("/api/orders?page=1&page_size=101")
    assert response.status_code == 400
