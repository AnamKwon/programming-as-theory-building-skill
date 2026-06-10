"""Integration tests for FastAPI endpoints."""

import pytest
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db, Base
from src.commerce_service.service import CommerceService


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


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, auth_headers, db):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["initial_stock"] == 100


def test_create_sku_missing_token(client, db):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_token(client, db):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -10},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 90


def test_create_reservation_success(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "unique-1"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 30)

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "unique-1"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_idempotent_reservation(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "unique-1"},
        headers=auth_headers,
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "unique-1"},
        headers=auth_headers,
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]

    sku = service.sku_repo.get_sku_by_code("SKU-001")
    assert sku.available_stock == 50


def test_confirm_reservation_success(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "unique-1")

    response = client.post(
        f"/reservations/{reservation.id}/confirm",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation.id


def test_confirm_expired_reservation(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "unique-1")

    reservation.created_at = datetime.utcnow() - timedelta(seconds=310)
    db.commit()

    response = client.post(
        f"/reservations/{reservation.id}/confirm",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"

    updated = service.reservation_repo.get_reservation_by_id(reservation.id)
    assert updated.status == "EXPIRED"

    sku = service.sku_repo.get_sku_by_code("SKU-001")
    assert sku.available_stock == 100


def test_confirm_non_pending_reservation(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "unique-1")
    service.confirm_reservation(reservation.id)

    response = client.post(
        f"/reservations/{reservation.id}/confirm",
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_cancel_reservation_success(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "unique-1")

    response = client.post(
        f"/reservations/{reservation.id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 200

    updated = service.reservation_repo.get_reservation_by_id(reservation.id)
    assert updated.status == "CANCELLED"

    sku = service.sku_repo.get_sku_by_code("SKU-001")
    assert sku.available_stock == 100


def test_cancel_non_pending_reservation(client, auth_headers, db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 50, "unique-1")
    service.confirm_reservation(reservation.id)

    response = client.post(
        f"/reservations/{reservation.id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_get_orders_pagination(client, db):
    service = CommerceService(db)
    for i in range(25):
        service.create_sku(f"SKU-{i}", 100)
        reservation, _ = service.create_reservation(f"SKU-{i}", 10, f"unique-{i}")
        service.confirm_reservation(reservation.id)

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["total"] == 25
    assert data1["page"] == 1

    response2 = client.get("/orders?page=2&size=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 10
    assert data2["page"] == 2

    response3 = client.get("/orders?page=3&size=10")
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["orders"]) == 5
    assert data3["page"] == 3


def test_get_orders_default_pagination(client, db):
    service = CommerceService(db)
    for i in range(5):
        service.create_sku(f"SKU-{i}", 100)
        reservation, _ = service.create_reservation(f"SKU-{i}", 10, f"unique-{i}")
        service.confirm_reservation(reservation.id)

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 10


def test_happy_path_workflow(client, auth_headers, db):
    service = CommerceService(db)

    response1 = client.post(
        "/skus",
        json={"sku": "PRODUCT-123", "initial_stock": 100},
        headers=auth_headers,
    )
    assert response1.status_code == 201

    response2 = client.post(
        "/reservations",
        json={"sku": "PRODUCT-123", "quantity": 30, "idempotency_key": "order-1"},
        headers=auth_headers,
    )
    assert response2.status_code == 201
    reservation_id = response2.json()["id"]

    response3 = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers,
    )
    assert response3.status_code == 200

    response4 = client.get("/orders")
    assert response4.status_code == 200
    orders = response4.json()
    assert orders["total"] == 1
    assert orders["orders"][0]["reservation_id"] == reservation_id
