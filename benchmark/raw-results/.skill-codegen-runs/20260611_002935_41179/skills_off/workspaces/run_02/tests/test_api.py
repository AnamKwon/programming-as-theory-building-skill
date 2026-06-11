import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from commerce_service.models import Base, Reservation

VALID_API_KEY = "test-api-key-12345"
INVALID_API_KEY = "invalid-key"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": INVALID_API_KEY},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_negative(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["quantity"] == 30


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 20},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 50,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client, test_app):
    from sqlalchemy.orm import sessionmaker

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res.json()["id"]

    SessionLocal = sessionmaker(bind=test_app.state.engine)
    db = SessionLocal()

    old_time = datetime.utcnow() - timedelta(seconds=301)
    db.query(Reservation).filter(Reservation.id == reservation_id).update(
        {"created_at": old_time}
    )
    db.commit()
    db.close()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "idempotency-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )

    sku_response = client.post(
        "/skus",
        json={"sku": "SKU001_CHECK", "initial_stock": 0},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert sku_response.status_code == 201


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY},
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 10,
                "idempotency_key": f"idempotency-{i}",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

    response1 = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["total"] == 25

    response2 = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 10

    response3 = client.get(
        "/orders?page=3&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["orders"]) == 5


def test_get_orders_requires_api_key(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_workflow_sku_reserve_confirm_order(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 30,
            "idempotency_key": "workflow-1",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res.status_code == 201
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert confirm_res.status_code == 200

    orders_res = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert orders_res.status_code == 200
    assert len(orders_res.json()["orders"]) == 1
    assert orders_res.json()["orders"][0]["reservation_id"] == reservation_id
