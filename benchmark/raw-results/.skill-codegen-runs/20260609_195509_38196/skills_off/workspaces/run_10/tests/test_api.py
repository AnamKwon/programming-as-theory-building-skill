import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
        return db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def api_headers():
    return {"X-API-Key": "test-api-key-123"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_sku(client, api_headers):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "SKU001"
    assert data["price"] == "19.99"
    assert data["stock_quantity"] == 100


def test_create_sku_without_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity_delta": 10},
        headers=api_headers,
    )
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 110


def test_create_reservation_happy_path(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
        },
        headers=api_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 5},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
        },
        headers=api_headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    res1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
            "idempotency_key": "idem-1",
        },
        headers=api_headers,
    )
    res_id_1 = res1.json()["id"]

    res2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
            "idempotency_key": "idem-1",
        },
        headers=api_headers,
    )
    res_id_2 = res2.json()["id"]

    assert res_id_1 == res_id_2
    assert res1.status_code == 201
    assert res2.status_code == 201


def test_confirm_reservation(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
        },
        headers=api_headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=api_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10


def test_cancel_reservation(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 10,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
        },
        headers=api_headers,
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=api_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_paginated(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 1000},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 1,
                "customer_id": f"customer{i}",
                "ttl_seconds": 3600,
            },
            headers=api_headers,
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=api_headers,
        )

    response = client.get("/orders?offset=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["offset"] == 0
    assert data["limit"] == 10

    response = client.get("/orders?offset=20&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_list_orders_default_pagination(client, api_headers):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "price": "19.99", "stock_quantity": 100},
        headers=api_headers,
    )
    sku_id = sku_response.json()["id"]

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 5,
            "customer_id": "customer1",
            "ttl_seconds": 3600,
        },
        headers=api_headers,
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=api_headers,
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["offset"] == 0
    assert data["limit"] == 20


def test_unauthorized_mutation_endpoints(client):
    endpoints_to_test = [
        ("POST", "/skus", {"code": "SKU001", "price": "19.99"}),
        ("POST", "/reservations", {"sku_id": 1, "quantity": 10, "customer_id": "test"}),
    ]

    for method, endpoint, payload in endpoints_to_test:
        if method == "POST":
            response = client.post(endpoint, json=payload)
            assert response.status_code == 403
