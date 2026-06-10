"""Tests for the API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import Base, app, get_db
from commerce_service.models import ReservationModel
from datetime import datetime, timedelta, timezone

DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

TEST_TOKEN = "test-token-12345"
INVALID_TOKEN = "invalid-token"


@pytest.fixture(autouse=True)
def clear_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success():
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["available_stock"] == 100


def test_create_sku_missing_token():
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_token():
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": INVALID_TOKEN},
    )
    assert response.status_code == 401


def test_adjust_stock_success():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": -20},
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 80


def test_adjust_stock_invalid_token():
    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": -20},
        headers={"X-API-Token": INVALID_TOKEN},
    )
    assert response.status_code == 401


def test_create_reservation_success():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 50},
        headers={"X-API-Token": TEST_TOKEN},
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 100,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    res1 = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 0},
        headers={"X-API-Token": TEST_TOKEN},
    )
    stock_before_retry = response.json()["available_stock"]

    res2 = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert res2.status_code == 201
    assert res2.json()["id"] == id1

    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 0},
        headers={"X-API-Token": TEST_TOKEN},
    )
    stock_after_retry = response.json()["available_stock"]
    assert stock_before_retry == stock_after_retry


def test_confirm_reservation_success():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 30
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_expired():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    reservation_id = res.json()["id"]

    db = next(override_get_db())
    res_model = db.query(ReservationModel).filter_by(id=reservation_id).first()
    past_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    res_model.created_at = past_time.replace(tzinfo=None)
    db.commit()
    db.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 0},
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert sku_response.json()["available_stock"] == 100


def test_cancel_reservation_success():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 0},
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert sku_response.json()["available_stock"] == 100


def test_get_orders_empty():
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1


def test_get_orders_paginated():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={
                "sku": "WIDGET-001",
                "quantity": 1,
                "idempotency_key": f"key-{i}",
            },
            headers={"X-API-Token": TEST_TOKEN},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": TEST_TOKEN},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["pages"] == 3

    response = client.get("/orders?page=2&size=10")
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 2

    response = client.get("/orders?page=3&size=10")
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 3


def test_get_orders_no_auth_required():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Token": TEST_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    reservation_id = res.json()["id"]
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": TEST_TOKEN},
    )

    response = client.get("/orders")
    assert response.status_code == 200


def test_happy_path_workflow():
    client.post(
        "/skus",
        json={"sku": "GADGET-99", "initial_stock": 50},
        headers={"X-API-Token": TEST_TOKEN},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "GADGET-99",
            "quantity": 10,
            "idempotency_key": "order-123",
        },
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert res.status_code == 201
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Token": TEST_TOKEN},
    )
    assert confirm_res.status_code == 200
    order_id = confirm_res.json()["id"]

    orders_res = client.get("/orders")
    assert orders_res.status_code == 200
    orders = orders_res.json()["items"]
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
    assert orders[0]["sku"] == "GADGET-99"
    assert orders[0]["quantity"] == 10
