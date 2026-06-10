import pytest
import time
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app
from src.commerce_service.models import Base
from src.commerce_service.repository import get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

VALID_TOKEN = "test-api-token-secret"
INVALID_TOKEN = "wrong-token"


@pytest.fixture(autouse=True)
def cleanup_db():
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_missing_token():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_create_sku_invalid_token():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": INVALID_TOKEN},
    )
    assert response.status_code == 401


def test_adjust_stock_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_negative():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70


def test_adjust_stock_sku_not_found():
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 50},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 404


def test_create_reservation_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Token": VALID_TOKEN},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response1.status_code == 201
    res1_id = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response2.status_code == 201
    res2_id = response2.json()["id"]

    assert res1_id == res2_id

    sku_check = client.get("/orders", headers={"X-API-Token": VALID_TOKEN})
    assert sku_check.status_code == 200


def test_confirm_reservation_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["reservation_id"] == res_id


def test_confirm_reservation_expired():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_id = res.json()["id"]

    time.sleep(301)

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_confirm_non_pending_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400


def test_cancel_reservation_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_non_pending_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert response.status_code == 400


def test_get_orders_pagination():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 500},
        headers={"X-API-Token": VALID_TOKEN},
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Token": VALID_TOKEN},
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Token": VALID_TOKEN},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["pages"] == 2

    response = client.get("/orders?page=2&size=10")
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2


def test_happy_path_workflow():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Token": VALID_TOKEN},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert res.status_code == 201
    res_id = res.json()["id"]

    confirm = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Token": VALID_TOKEN},
    )
    assert confirm.status_code == 200
    order_id = confirm.json()["id"]

    orders = client.get("/orders")
    assert orders.status_code == 200
    data = orders.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == order_id
