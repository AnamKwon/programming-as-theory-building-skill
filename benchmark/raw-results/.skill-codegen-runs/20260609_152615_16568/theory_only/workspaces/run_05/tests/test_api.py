import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, Base, get_db


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
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["sku_id"] == "SKU001"


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity_delta": 50},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 150


def test_reserve_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 50
    assert data["state"] == "pending"
    assert data["is_new"] is True


def test_reserve_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 30},
        headers={"X-API-Key": "dev-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 409


def test_reserve_idempotent_retry(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    response1 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    res1_id = response1.json()["reservation_id"]

    response2 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    res2_id = response2.json()["reservation_id"]
    is_new = response2.json()["is_new"]

    assert res1_id == res2_id
    assert is_new is False


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    res_id = res_resp.json()["reservation_id"]

    confirm_resp = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "dev-key"},
    )
    assert confirm_resp.status_code == 200
    data = confirm_resp.json()
    assert data["state"] == "confirmed"
    assert data["order_id"] is not None


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    res_id = res_resp.json()["reservation_id"]

    cancel_resp = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "dev-key"},
    )
    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["state"] == "cancelled"


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "dev-key"},
    )
    res_id = res_resp.json()["reservation_id"]

    confirm_resp = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "dev-key"},
    )
    order_id = confirm_resp.json()["order_id"]

    get_resp = client.get(f"/orders/{order_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == order_id
    assert data["state"] == "confirmed"


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 1000},
        headers={"X-API-Key": "dev-key"},
    )

    # Create 15 orders
    for i in range(15):
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "dev-key"},
        )
        res_id = res_resp.json()["reservation_id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "dev-key"},
        )

    # Test default pagination (limit=10)
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["skip"] == 0
    assert data["limit"] == 10

    # Test second page
    response = client.get("/orders?skip=10&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["skip"] == 10


def test_get_nonexistent_order(client):
    response = client.get("/orders/nonexistent")
    assert response.status_code == 404


def test_reserve_unauthorized(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
    )
    assert response.status_code == 403
