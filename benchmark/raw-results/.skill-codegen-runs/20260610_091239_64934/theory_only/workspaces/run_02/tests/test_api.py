import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, engine, SessionLocal, get_db
from commerce_service.models import Base

client = TestClient(app)
API_KEY = "test-key-123"


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_happy_path():
    response = client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "sku-001"
    assert data["name"] == "Widget"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_unauthorized():
    response = client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_key():
    response = client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_adjust_stock():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/skus/sku-001/adjust-stock",
        json={"quantity": 50},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_nonexistent_sku():
    response = client.post(
        "/skus/sku-nonexistent/adjust-stock",
        json={"quantity": 50},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 404


def test_create_reservation_happy_path():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "sku-001"
    assert data["quantity"] == 10
    assert data["status"] == "active"


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 5},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_unauthorized():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
    )
    assert response.status_code == 403


def test_confirm_reservation_happy_path():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"
    assert data["reservation_id"] == reservation_id


def test_confirm_nonexistent_reservation():
    response = client.post(
        "/reservations/nonexistent-id/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 404


def test_cancel_reservation_happy_path():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_cancel_reservation_unauthorized():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
    )
    assert response.status_code == 403


def test_get_order():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    order_id = confirm_response.json()["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["sku_id"] == "sku-001"
    assert data["status"] == "confirmed"


def test_get_nonexistent_order():
    response = client.get("/orders/nonexistent-id")
    assert response.status_code == 404


def test_list_orders_pagination():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 1000},
        headers={"X-API-Key": API_KEY},
    )

    for _ in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "sku-001", "quantity": 5},
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    response = client.get("/orders?offset=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["offset"] == 0
    assert data["limit"] == 10

    response = client.get("/orders?offset=20&limit=10")
    data = response.json()
    assert len(data["orders"]) == 5


def test_list_orders_default_pagination():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_list_orders_invalid_limit():
    response = client.get("/orders?limit=1000")
    assert response.status_code == 422


def test_idempotent_reservation_with_key():
    client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    idempotency_key = "unique-key-123"

    response1 = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10, "idempotency_key": idempotency_key},
        headers={"X-API-Key": API_KEY},
    )
    assert response1.status_code == 201
    reservation_id_1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku_id": "sku-001", "quantity": 10, "idempotency_key": idempotency_key},
        headers={"X-API-Key": API_KEY},
    )
    assert response2.status_code == 201
    reservation_id_2 = response2.json()["id"]

    assert reservation_id_1 == reservation_id_2
