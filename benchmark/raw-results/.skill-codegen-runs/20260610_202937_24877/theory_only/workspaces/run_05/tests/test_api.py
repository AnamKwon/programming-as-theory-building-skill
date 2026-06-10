import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.commerce_service.models import Base, Reservation
from src.commerce_service.app import app, get_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(db):
    def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus", json={"sku": "SKU001", "initial_stock": 100}
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
        headers={"X-API-Key": "test-api-key-12345"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -10},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 90


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["quantity"] == 10


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 5},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    res2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client, db):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    res_id = res.json()["id"]

    db.query(Reservation).filter(Reservation.id == res_id).update(
        {"created_at": datetime.utcnow() - timedelta(seconds=301)}
    )
    db.commit()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"idem-{i}"},
            headers={"X-API-Key": "test-api-key-12345"},
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "test-api-key-12345"},
        )

    response = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["size"] == 10

    response2 = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 10

    response3 = client.get(
        "/orders?page=3&size=10",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["items"]) == 5


def test_unauthorized_mutation_blocks(client):
    response = client.post(
        "/skus", json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust", json={"sku": "SKU001", "amount": -10}
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
    )
    assert response.status_code == 401

    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    res_id = res.json()["id"]
    assert res.json()["status"] == "PENDING"

    confirm_res = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert confirm_res.json()["status"] == "CONFIRMED"

    orders = client.get(
        "/orders",
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert orders.status_code == 200
    assert len(orders.json()["items"]) == 1
    assert orders.json()["items"][0]["quantity"] == 10
