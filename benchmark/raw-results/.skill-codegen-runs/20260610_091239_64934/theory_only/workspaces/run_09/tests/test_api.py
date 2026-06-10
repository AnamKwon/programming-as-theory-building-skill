import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_repository
from src.commerce_service.models import ReservationStatus
from src.commerce_service.repository import Repository


@pytest.fixture
def client(db_session):
    def override_get_repository():
        try:
            yield Repository(db_session)
        finally:
            pass

    app.dependency_overrides[get_repository] = override_get_repository
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1", "description": "A product"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU001"
    assert data["name"] == "Product 1"


def test_create_sku_without_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
    )
    assert response.status_code == 403
    assert "API key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_create_sku_duplicate(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 2"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 409


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )

    response = client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available"] == 100
    assert data["reserved"] == 0


def test_adjust_stock_nonexistent_sku(client):
    response = client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 404


def test_adjust_stock_negative_fails(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 50},
        headers={"X-API-Key": "dev-key-12345"},
    )

    response = client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": -100},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 400


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 5},
        headers={"X-API-Key": "dev-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10},
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_with_idempotency_key(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku_code": "SKU001",
            "quantity": 10,
            "idempotency_key": "key-001",
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response1.status_code == 201

    response2 = client.post(
        "/reservations",
        json={
            "sku_code": "SKU001",
            "quantity": 10,
            "idempotency_key": "key-001",
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10},
        headers={"X-API-Key": "dev-key-12345"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation"]["status"] == ReservationStatus.CONFIRMED
    assert data["order"]["status"] == "pending"


def test_confirm_reservation_expired(client, db_session):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={
            "sku_code": "SKU001",
            "quantity": 10,
            "reservation_duration_seconds": 60,
        },
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert res.status_code == 201
    reservation_id = res.json()["id"]

    # Manually expire the reservation by updating its expires_at in the database
    from datetime import datetime
    from sqlalchemy import update
    from src.commerce_service.models import ReservationModel
    db_session.execute(
        update(ReservationModel)
        .where(ReservationModel.id == reservation_id)
        .values(expires_at=datetime.utcnow())
    )
    db_session.commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 410
    assert "expired" in response.json()["detail"].lower()


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10},
        headers={"X-API-Key": "dev-key-12345"},
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "dev-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == ReservationStatus.CANCELLED


def test_list_orders_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 1000},
        headers={"X-API-Key": "dev-key-12345"},
    )

    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_code": "SKU001", "quantity": 10},
            headers={"X-API-Key": "dev-key-12345"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "dev-key-12345"},
        )

    response = client.get("/orders?offset=0&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 3
    assert data["total"] == 5
    assert data["offset"] == 0
    assert data["limit"] == 3


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 1000},
        headers={"X-API-Key": "dev-key-12345"},
    )

    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_code": "SKU001", "quantity": 10},
            headers={"X-API-Key": "dev-key-12345"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "dev-key-12345"},
        )

    response = client.get("/orders?offset=3&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 2


def test_get_order_success(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "dev-key-12345"},
    )
    client.post(
        "/stocks/adjust",
        json={"sku_code": "SKU001", "quantity": 100},
        headers={"X-API-Key": "dev-key-12345"},
    )

    res = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10},
        headers={"X-API-Key": "dev-key-12345"},
    )
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "dev-key-12345"},
    )
    order_id = confirm_res.json()["order"]["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["sku_code"] == "SKU001"


def test_get_order_nonexistent(client):
    response = client.get("/orders/999")
    assert response.status_code == 404
