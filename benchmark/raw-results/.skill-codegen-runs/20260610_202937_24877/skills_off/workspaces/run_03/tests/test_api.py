import pytest
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app
from src.commerce_service.repository import Base, get_db


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
    yield TestClient(app)
    app.dependency_overrides.clear()


API_KEY = "test-api-key-12345"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -20},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 80


def test_adjust_stock_unauthorized(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -20},
    )
    assert response.status_code == 401


def test_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    assert res_response.status_code == 201
    reservation = res_response.json()
    assert reservation["sku"] == "SKU001"
    assert reservation["quantity"] == 30
    assert reservation["status"] == "PENDING"
    reservation_id = reservation["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["status"] == "CONFIRMED"

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert len(orders_data["items"]) == 1
    assert orders_data["items"][0]["reservation_id"] == reservation_id


def test_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 20},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_data = {"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"}

    res1 = client.post(
        "/reservations",
        json=res_data,
        headers={"X-API-Key": API_KEY},
    )
    assert res1.status_code == 201
    res1_data = res1.json()
    res1_id = res1_data["id"]

    res2 = client.post(
        "/reservations",
        json=res_data,
        headers={"X-API-Key": API_KEY},
    )
    assert res2.status_code == 201
    res2_data = res2.json()
    res2_id = res2_data["id"]

    assert res1_id == res2_id
    assert res1_data == res2_data


def test_reservation_unauthorized(client):
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
    )
    assert response.status_code == 401


def test_confirm_reservation_expired(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    from src.commerce_service.repository import SessionLocal
    from src.commerce_service.repository import Reservation

    db = SessionLocal()
    db_res = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    db_res.created_at = datetime.utcnow() - timedelta(seconds=301)
    db.commit()
    db.close()

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert confirm_response.status_code == 400
    assert confirm_response.json()["detail"] == "Reservation expired"

    orders_response = client.get("/orders")
    orders_data = orders_response.json()
    assert orders_data["total"] == 0


def test_confirm_reservation_invalid_state(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    confirm_again = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert confirm_again.status_code == 400
    assert confirm_again.json()["detail"] == "Reservation is not in PENDING state"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )

    res_response_2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key456"},
        headers={"X-API-Key": API_KEY},
    )
    assert res_response_2.status_code == 201


def test_cancel_reservation_invalid_state(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
        headers={"X-API-Key": API_KEY},
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert cancel_response.status_code == 400
    assert cancel_response.json()["detail"] == "Reservation is not in PENDING state"


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key{i}"},
            headers={"X-API-Key": API_KEY},
        )
        reservation = res_response.json()
        client.post(
            f"/reservations/{reservation['id']}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25
    assert len(data["items"]) == 10

    response = client.get("/orders?page=2&size=10")
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 10

    response = client.get("/orders?page=3&size=10")
    data = response.json()
    assert data["page"] == 3
    assert len(data["items"]) == 5
