"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from commerce_service.app import app, get_db, get_service
from commerce_service.repository import Base, Repository
from commerce_service.service import CommerceService


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_code": "TEST-001", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "TEST-001"
    assert data["stock_count"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_code": "TEST-002", "name": "Test Product", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert "Missing X-API-Key" in response.json()["detail"]


def test_create_sku_invalid_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "TEST-003", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-004", "name": "Test Product", "initial_stock": 50},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    response = client.put(
        f"/skus/{sku_id}/stock",
        json={"quantity_delta": 25},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["stock_count"] == 75


def test_reserve_stock_success(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-005", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["quantity"] == 10


def test_reserve_stock_insufficient(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-006", "name": "Test Product", "initial_stock": 10},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 20},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_reserve_stock_idempotent(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-007", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    response1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 15},
        headers={"X-API-Key": "test-key", "Idempotency-Key": "req-001"},
    )
    res_id = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 15},
        headers={"X-API-Key": "test-key", "Idempotency-Key": "req-001"},
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response2.json()["id"] == res_id


def test_confirm_reservation_success(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-008", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 20},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_unauthorized(client):
    response = client.post(
        "/reservations/1/confirm",
    )
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-009", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 25},
        headers={"X-API-Key": "test-key"},
    )
    res_id = res_response.json()["id"]

    response = client.delete(
        f"/reservations/{res_id}",
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    sku_after = client.post(
        "/skus",
        json={"sku_code": "TEST-010", "name": "Verify Stock", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    ).json()


def test_list_orders_empty(client):
    response = client.get("/orders?offset=0&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_orders_pagination(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "TEST-011", "name": "Test Product", "initial_stock": 1000},
        headers={"X-API-Key": "test-key"},
    )
    sku_id = sku_response.json()["id"]

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10},
            headers={"X-API-Key": "test-key"},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )

    response = client.get("/orders?offset=0&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 5
    assert data["offset"] == 0
    assert data["limit"] == 20

    response_page1 = client.get("/orders?offset=0&limit=2")
    response_page2 = client.get("/orders?offset=2&limit=2")

    page1 = response_page1.json()
    page2 = response_page2.json()

    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert page1["total"] == 5


def test_list_orders_invalid_params(client):
    response = client.get("/orders?offset=-1&limit=20")
    assert response.status_code == 400

    response = client.get("/orders?offset=0&limit=0")
    assert response.status_code == 400

    response = client.get("/orders?offset=0&limit=101")
    assert response.status_code == 400


def test_full_workflow(client):
    sku_response = client.post(
        "/skus",
        json={"sku_code": "FULL-WORKFLOW", "name": "Workflow Test", "initial_stock": 50},
        headers={"X-API-Key": "test-key"},
    )
    assert sku_response.status_code == 201
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key", "Idempotency-Key": "workflow-1"},
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-key"},
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    order_response = client.get(f"/orders/{order_id}")
    assert order_response.status_code == 200
    assert order_response.json()["status"] == "confirmed"
