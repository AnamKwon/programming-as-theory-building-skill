import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base
from commerce_service.app import app, get_db


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def api_key():
    os.environ["COMMERCE_API_KEY"] = "test-key"
    return "test-key"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["stock_available"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
    )
    assert response.status_code == 403


def test_create_sku_bad_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/skus/SKU-001/stock",
        json={"quantity_delta": -30},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["stock_available"] == 70


def test_adjust_stock_not_found(client, api_key):
    response = client.post(
        "/skus/MISSING/stock",
        json={"quantity_delta": -30},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_create_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["state"] == "pending"


def test_create_reservation_insufficient_stock(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 30},
        headers={"X-API-Key": api_key},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": api_key},
    )
    res1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-001",
        },
        headers={"X-API-Key": api_key},
    )
    res2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-001",
        },
        headers={"X-API-Key": api_key},
    )
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["reservation_id"] == res2.json()["reservation_id"]


def test_confirm_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": api_key},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    res_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"


def test_confirm_reservation_not_found(client, api_key):
    response = client.post(
        "/reservations/MISSING/confirm",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 100},
        headers={"X-API-Key": api_key},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 50},
        headers={"X-API-Key": api_key},
    )
    res_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_cancel_reservation_not_found(client, api_key):
    response = client.post(
        "/reservations/MISSING/cancel",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["skip"] == 0
    assert data["limit"] == 10


def test_list_orders_with_pagination(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 1000},
        headers={"X-API-Key": api_key},
    )

    # Create 5 reservations and confirm them
    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10},
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )

    response = client.get("/orders?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["skip"] == 0
    assert data["limit"] == 2

    response = client.get("/orders?skip=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2

    response = client.get("/orders?skip=4&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1


def test_list_orders_limit_capped(client, api_key):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "stock_available": 1000},
        headers={"X-API-Key": api_key},
    )

    response = client.get("/orders?limit=200")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 100
