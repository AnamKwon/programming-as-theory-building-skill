import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.repository import Base


@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield SessionLocal()
    os.unlink(db_path)


@pytest.fixture
def client(temp_db):
    return TestClient(app)


def get_headers(api_key="test-key-123"):
    return {"Authorization": f"Bearer {api_key}"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    headers = get_headers()
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=get_headers("wrong-key"),
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_create_reservation_success(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=headers)

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 30}, headers=headers)

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=headers)

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )
    res2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )

    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation_success(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/confirm", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["reservation"]["status"] == "CONFIRMED"
    assert data["order"]["reservation_id"] == reservation_id


def test_confirm_reservation_expired(client, temp_db):
    from datetime import datetime, timezone, timedelta
    from src.commerce_service.repository import Reservation

    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    reservation = temp_db.query(Reservation).filter(Reservation.id == reservation_id).first()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = old_time
    temp_db.commit()

    response = client.post(f"/reservations/{reservation_id}/confirm", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_cancel_reservation_success(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders_pagination(client):
    headers = get_headers()
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 1000}, headers=headers)

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"idem-{i}"},
            headers=headers,
        )
        reservation_id = res_response.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    response = client.get("/orders?page=1&size=10", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25

    response = client.get("/orders?page=2&size=10", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 2

    response = client.get("/orders?page=3&size=10", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["page"] == 3


def test_unauthorized_endpoints(client):
    wrong_headers = get_headers("wrong-key")

    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers=wrong_headers,
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers=wrong_headers,
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        headers=wrong_headers,
    )
    assert response.status_code == 401


def test_workflow_sku_reserve_confirm_order(client):
    headers = get_headers()

    sku_response = client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=headers,
    )
    assert sku_response.status_code == 201

    res_response = client.post(
        "/reservations",
        json={"sku": "PROD-001", "quantity": 30, "idempotency_key": "order-123"},
        headers=headers,
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders", headers=headers)
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert len(data["orders"]) == 1
    assert data["orders"][0]["reservation_id"] == reservation_id
