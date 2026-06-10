import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    return db


@pytest.fixture
def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def valid_api_key():
    return "sk-commerce-test-key-123"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, valid_api_key):
    response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "TEST-SKU-001"
    assert data["quantity_available"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
    )
    assert response.status_code == 422


def test_adjust_stock_success(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.patch(
        f"/skus/{sku_id}/stock",
        json={"adjustment": -10},
        headers={"x-api-key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["quantity_available"] == 90


def test_create_reservation_success(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"x-api-key": valid_api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 150, "idempotency_key": "key-1"},
        headers={"x-api-key": valid_api_key},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent_retry(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    res1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"x-api-key": valid_api_key},
    )
    assert res1.status_code == 201
    reservation_id_1 = res1.json()["id"]

    res2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"x-api-key": valid_api_key},
    )
    assert res2.status_code == 201
    assert res2.json()["id"] == reservation_id_1


def test_confirm_reservation_success(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"x-api-key": valid_api_key},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation_success(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key-1"},
        headers={"x-api-key": valid_api_key},
    )
    reservation_id = res_response.json()["id"]

    response = client.delete(
        f"/reservations/{reservation_id}",
        headers={"x-api-key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_orders_success(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 1000},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"x-api-key": valid_api_key},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": valid_api_key},
        )

    response = client.get("/orders?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["has_more"] is True
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_get_orders_pagination(client, valid_api_key):
    sku_response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 1000},
        headers={"x-api-key": valid_api_key},
    )
    sku_id = sku_response.json()["id"]

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"x-api-key": valid_api_key},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": valid_api_key},
        )

    response = client.get("/orders?page=3&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["has_more"] is False


def test_mutation_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "TEST-SKU-001", "quantity_available": 100},
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 401
