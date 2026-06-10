import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service import models

engine = models.engine
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
VALID_KEY = "test-key-123"


@pytest.fixture
def reset_db():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    yield
    models.Base.metadata.drop_all(bind=engine)


def test_health_check(reset_db):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_sku_success(reset_db):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "SKU001"
    assert data["name"] == "Product"


def test_create_sku_unauthorized(reset_db):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
    )
    assert response.status_code == 403


def test_create_sku_invalid_key(reset_db):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 100


def test_adjust_stock_nonexistent_sku(reset_db):
    response = client.post(
        "/stock/adjust",
        json={"sku_id": "NONEXISTENT", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 400


def test_create_reservation_success(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 10},
        headers={"X-API-Key": VALID_KEY},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 50,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_idempotent_reservation_retry(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )

    res1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    res2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert res2.status_code == 201
    id2 = res2.json()["id"]

    assert id1 == id2


def test_confirm_reservation_success(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation_success(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_confirmed_reservation_fails(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_KEY},
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 400


def test_get_order(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
        headers={"X-API-Key": VALID_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    order_id = res.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "reserved"


def test_list_orders_pagination(reset_db):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
        headers={"X-API-Key": VALID_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 1000},
        headers={"X-API-Key": VALID_KEY},
    )

    for i in range(25):
        client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": f"key-{i}",
            },
            headers={"X-API-Key": VALID_KEY},
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["limit"] == 10
    assert data["offset"] == 0

    response = client.get("/orders?limit=10&offset=20")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_unauthorized_mutation_endpoints(reset_db):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Product", "price": "99.99"},
    )
    assert response.status_code == 403

    response = client.post(
        "/stock/adjust",
        json={"sku_id": "SKU001", "quantity": 100},
    )
    assert response.status_code == 403

    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
    )
    assert response.status_code == 403
