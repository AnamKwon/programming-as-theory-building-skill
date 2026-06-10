import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base
from commerce_service.app import app, get_db


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_sku_unauthorized(client):
    response = client.post("/skus", json={"code": "SKU001", "name": "Product A"})
    assert response.status_code == 403


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SKU001"
    assert data["name"] == "Product A"
    assert "id" in data


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "invalid-key"},
    )
    assert response.status_code == 403


def test_adjust_stock(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    response = client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 100
    assert data["reserved"] == 0


def test_get_stock(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )

    response = client.get(f"/skus/{sku_id}/stock")
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 100
    assert data["reserved"] == 0


def test_create_reservation_happy_path(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 50
    assert data["confirmed"] is False


def test_create_reservation_insufficient_stock(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 30},
        headers={"x-api-key": "test-api-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )

    response1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation_happy_path(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PENDING"
    assert "id" in data


def test_confirm_reservation_unauthorized(client):
    response = client.post("/reservations/nonexistent/confirm")
    assert response.status_code == 403


def test_cancel_reservation_happy_path(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    reservation_id = res_response.json()["id"]

    response = client.delete(
        f"/reservations/{reservation_id}/cancel",
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 404

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"x-api-key": "test-api-key-123"},
    )
    assert response.status_code == 204


def test_cancel_reservation_unauthorized(client):
    response = client.post("/reservations/nonexistent/cancel")
    assert response.status_code == 403


def test_get_order(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 100},
        headers={"x-api-key": "test-api-key-123"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "req-1"},
        headers={"x-api-key": "test-api-key-123"},
    )
    reservation_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"x-api-key": "test-api-key-123"},
    )
    order_id = order_response.json()["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["status"] == "PENDING"


def test_list_orders_pagination(client):
    sku_response = client.post(
        "/skus",
        json={"code": "SKU001", "name": "Product A"},
        headers={"x-api-key": "test-api-key-123"},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        f"/skus/{sku_id}/stock",
        json={"quantity": 1000},
        headers={"x-api-key": "test-api-key-123"},
    )

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"req-{i}"},
            headers={"x-api-key": "test-api-key-123"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"x-api-key": "test-api-key-123"},
        )

    response = client.get("/orders?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0

    response = client.get("/orders?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2

    response = client.get("/orders?limit=2&offset=4")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 1
