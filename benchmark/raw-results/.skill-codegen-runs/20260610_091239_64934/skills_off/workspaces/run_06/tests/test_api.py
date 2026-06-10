import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU-001"
    assert data["stock_quantity"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_create_duplicate_sku(client):
    headers = {"X-API-Key": "test-key-123"}
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    )
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Another", "stock_quantity": 50},
        headers=headers,
    )
    assert response.status_code == 409


def test_adjust_stock(client):
    headers = {"X-API-Key": "test-key-123"}
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/adjust-stock",
        json={"adjustment": 50},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 150


def test_create_reservation_success(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    response = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["quantity"] == 30
    assert response.json()["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    response = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 150},
        headers=headers,
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    res1 = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30, "idempotency_key": "key-123"},
        headers=headers,
    ).json()

    res2 = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30, "idempotency_key": "key-123"},
        headers=headers,
    ).json()

    assert res1["id"] == res2["id"]


def test_confirm_reservation(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    reservation = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30},
        headers=headers,
    ).json()

    response = client.post(
        f"/reservations/{reservation['id']}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_non_pending_reservation(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    reservation = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30},
        headers=headers,
    ).json()

    client.post(f"/reservations/{reservation['id']}/confirm", headers=headers)
    response = client.post(f"/reservations/{reservation['id']}/confirm", headers=headers)
    assert response.status_code == 400


def test_cancel_reservation(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    reservation = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30},
        headers=headers,
    ).json()

    response = client.post(
        f"/reservations/{reservation['id']}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_non_pending_reservation(client):
    headers = {"X-API-Key": "test-key-123"}
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "name": "Product", "stock_quantity": 100},
        headers=headers,
    ).json()

    reservation = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 30},
        headers=headers,
    ).json()

    client.post(f"/reservations/{reservation['id']}/cancel", headers=headers)
    response = client.post(f"/reservations/{reservation['id']}/cancel", headers=headers)
    assert response.status_code == 400


def test_list_orders_pagination(client):
    headers = {"X-API-Key": "test-key-123"}
    db = client.app.dependency_overrides[get_db]()

    from src.commerce_service.models import Order
    for _ in range(25):
        order = Order()
        db.add(order)
    db.commit()

    response = client.get("/orders?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["total_pages"] == 3


def test_list_orders_invalid_pagination(client):
    response = client.get("/orders?page=0&page_size=10")
    assert response.status_code == 422


def test_list_orders_page_size_limit(client):
    response = client.get("/orders?page=1&page_size=200")
    assert response.status_code == 422
