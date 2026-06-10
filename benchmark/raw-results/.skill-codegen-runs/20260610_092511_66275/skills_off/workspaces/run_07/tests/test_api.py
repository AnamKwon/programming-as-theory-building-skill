import pytest
import os
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import SessionLocal, init_db
from commerce_service.models import SKUCreate, ReservationCreate

API_KEY = os.getenv("API_KEY", "test-api-key-12345")


@pytest.fixture(scope="function")
def client():
    init_db()
    yield TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Widget", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU001"
    assert data["name"] == "Widget"
    assert data["stock_count"] == 100
    assert "id" in data


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Widget", "stock_count": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Widget", "stock_count": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU002", "name": "Gadget", "stock_count": 50},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_delta": 25},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock_count"] == 75


def test_adjust_stock_sku_not_found(client):
    response = client.post(
        "/stock/adjust",
        json={"sku_id": 9999, "quantity_delta": 10},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU003", "name": "Product", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "req-123"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
    assert data["state"] == "pending"
    assert "expires_at" in data
    assert "id" in data


def test_create_reservation_insufficient_stock(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU004", "name": "Limited", "stock_count": 5},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "req-456"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent_retry(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU005", "name": "Idempotent", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    first_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idempotent-key"},
        headers={"X-API-Key": API_KEY},
    )
    assert first_response.status_code == 201
    first_id = first_response.json()["id"]

    second_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idempotent-key"},
        headers={"X-API-Key": API_KEY},
    )
    assert second_response.status_code == 201
    assert second_response.json()["id"] == first_id


def test_create_reservation_idempotency_key_conflict(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU006", "name": "Conflict", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "conflict-key"},
        headers={"X-API-Key": API_KEY},
    )

    conflict_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 5, "idempotency_key": "conflict-key"},
        headers={"X-API-Key": API_KEY},
    )
    assert conflict_response.status_code == 409


def test_confirm_reservation_success(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU007", "name": "Confirmable", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "conf-123"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation"]["state"] == "pending"
    assert data["order"]["state"] == "confirmed"


def test_confirm_reservation_expired(client):
    from datetime import datetime, timedelta
    from commerce_service.repository import SessionLocal, ReservationModel

    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU008", "name": "Expirable", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "exp-123"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_resp.json()["id"]

    db = SessionLocal()
    reservation = db.query(ReservationModel).filter(ReservationModel.id == res_id).first()
    reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_cancel_reservation_success(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU009", "name": "Cancellable", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "can-123"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_resp.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "cancelled"


def test_get_order_success(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU010", "name": "Orderable", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "order-123"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_resp.json()["id"]

    conf_resp = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    order_id = conf_resp.json()["order"]["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["sku_id"] == sku_id
    assert data["state"] == "confirmed"


def test_get_order_not_found(client):
    response = client.get("/orders/9999")
    assert response.status_code == 404


def test_list_orders_pagination(client):
    sku_resp = client.post(
        "/skus",
        json={"sku_code": "SKU011", "name": "Pageable", "stock_count": 100},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_resp.json()["id"]

    for i in range(5):
        res_resp = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 2, "idempotency_key": f"page-{i}"},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    response = client.get("/orders?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2

    response = client.get("/orders?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["page"] == 2


def test_list_orders_invalid_pagination(client):
    response = client.get("/orders?page=0&page_size=10")
    assert response.status_code == 400

    response = client.get("/orders?page=1&page_size=0")
    assert response.status_code == 400


def test_unauthorized_mutation_without_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU012", "name": "Unauthorized", "stock_count": 100},
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku_id": 1, "quantity_delta": 10},
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 10, "idempotency_key": "no-key"},
    )
    assert response.status_code == 401
