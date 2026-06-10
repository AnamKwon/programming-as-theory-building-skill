import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app, _service
from src.commerce_service.models import ReservationState


@pytest.fixture
def client():
    from src.commerce_service.repository import Repository
    from src.commerce_service.service import CommerceService
    import src.commerce_service.app as app_module

    repo = Repository()
    service = CommerceService(repo)
    app_module._repo = repo
    app_module._service = service
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "WIDGET-001"
    assert data["name"] == "Blue Widget"
    assert data["total_stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
    )
    assert response.status_code == 403
    assert "Invalid or missing API key" in response.json()["detail"]


def test_create_sku_wrong_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    response = client.patch(
        "/skus/WIDGET-001/adjust-stock",
        json={"quantity_delta": 50},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["total_stock"] == 150


def test_adjust_stock_not_found(client):
    response = client.patch(
        "/skus/NONEXISTENT/adjust-stock",
        json={"quantity_delta": 50},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    response = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "cust-123"
    assert data["sku_id"] == "WIDGET-001"
    assert data["quantity"] == 10
    assert data["state"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 5},
        headers={"X-API-Key": "dev-key"},
    )
    response = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    res1 = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    res2 = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["reservation_id"] == res2.json()["reservation_id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    res = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    res_id = res.json()["reservation_id"]
    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"


def test_confirm_reservation_unauthorized(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    res = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    res_id = res.json()["reservation_id"]
    response = client.post(f"/reservations/{res_id}/confirm")
    assert response.status_code == 403


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/nonexistent/confirm",
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    res = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    res_id = res.json()["reservation_id"]
    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_cancel_reservation_unauthorized(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    res = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    res_id = res.json()["reservation_id"]
    response = client.post(f"/reservations/{res_id}/cancel")
    assert response.status_code == 403


def test_create_order_from_confirmed_reservation(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    res = client.post(
        "/reservations",
        json={
            "customer_id": "cust-123",
            "sku_id": "WIDGET-001",
            "quantity": 10,
            "idempotency_key": "key-1",
        },
    )
    res_id = res.json()["reservation_id"]
    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "dev-key"},
    )
    response = client.post(
        f"/reservations/{res_id}/create-order",
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["order_id"] is not None
    assert response.json()["reservation_id"] == res_id


def test_list_orders_success(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "customer_id": "cust-123",
                "sku_id": "WIDGET-001",
                "quantity": 1,
                "idempotency_key": f"key-{i}",
            },
        )
        res_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "dev-key"},
        )
        client.post(
            f"/reservations/{res_id}/create-order",
            headers={"X-API-Key": "dev-key"},
        )

    response = client.get("/orders", headers={"X-API-Key": "dev-key"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 15
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers={"X-API-Key": "dev-key"},
    )
    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "customer_id": "cust-123",
                "sku_id": "WIDGET-001",
                "quantity": 1,
                "idempotency_key": f"key-{i}",
            },
        )
        res_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "dev-key"},
        )
        client.post(
            f"/reservations/{res_id}/create-order",
            headers={"X-API-Key": "dev-key"},
        )

    response = client.get("/orders?limit=5&offset=10", headers={"X-API-Key": "dev-key"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["total"] == 15
    assert data["limit"] == 5
    assert data["offset"] == 10


def test_list_orders_unauthorized(client):
    response = client.get("/orders")
    assert response.status_code == 403
