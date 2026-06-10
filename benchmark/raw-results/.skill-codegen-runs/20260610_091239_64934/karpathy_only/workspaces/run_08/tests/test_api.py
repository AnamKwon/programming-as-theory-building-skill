import os
import pytest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service import models
from src.commerce_service.app import app, get_session


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_without_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_with_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["stock"] == 100


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.put(
        "/skus/SKU-001/stock",
        json={"delta": -10},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["stock"] == 90


def test_create_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "pending"
    assert "expires_at" in data


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 10},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_idempotent_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )

    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )

    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert "id" in data


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res_response.json()["id"]

    response = client.delete(
        f"/reservations/{reservation_id}",
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    sku_response = client.put(
        "/skus/SKU-001/stock",
        json={"delta": 0},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert sku_response.json()["stock"] == 100


def test_list_orders(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idem-{i}",
                "ttl_seconds": 3600,
            },
            headers={"X-API-Key": "test-key-12345"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key-12345"},
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idem-{i}",
                "ttl_seconds": 3600,
            },
            headers={"X-API-Key": "test-key-12345"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key-12345"},
        )

    response1 = client.get("/orders?limit=10&offset=0")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 10
    assert data1["total"] == 25

    response2 = client.get("/orders?limit=10&offset=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 10

    response3 = client.get("/orders?limit=10&offset=20")
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["items"]) == 5


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "stock": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1",
            "ttl_seconds": 3600,
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-12345"},
    )
    order_id = order_response.json()["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50


def test_get_order_not_found(client):
    response = client.get("/orders/999")
    assert response.status_code == 404
