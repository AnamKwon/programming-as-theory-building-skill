import pytest
import src.commerce_service.app as app_module
from fastapi.testclient import TestClient
from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    app_module._repo = Repository(db_path=":memory:")
    app_module._service = CommerceService(app_module._repo)
    return TestClient(app)


@pytest.fixture
def api_key():
    return "test-api-key"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, api_key):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_adjust_stock_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -10},
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 90


def test_adjust_stock_invalid_api_key(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -10},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_create_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 10},
        headers={"X-API-Key": api_key}
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 20, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    res_id_1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    res_id_2 = response2.json()["id"]

    assert response1.status_code == 201
    assert response2.status_code == 201
    assert res_id_1 == res_id_2

    sku_response = client.get(
        "/health"
    )
    assert sku_response.status_code == 200


def test_confirm_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1


def test_confirm_reservation_expired(client, api_key):
    from datetime import datetime, timedelta
    import sqlite3

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    res_id = res.json()["id"]

    reservation = app_module._repo.get_reservation(res_id)
    created_at = datetime.fromisoformat(reservation["created_at"])
    old_time = (created_at - timedelta(seconds=301)).isoformat()

    conn = app_module._repo._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reservation SET created_at = ? WHERE id = ?", (old_time, res_id))
    conn.commit()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]


def test_cancel_reservation_success(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": api_key}
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": api_key}
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_list_orders_pagination(client, api_key):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 200},
        headers={"X-API-Key": api_key}
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 5, "idempotency_key": f"idem-{i}"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key}
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 15
    assert len(data["orders"]) == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["orders"]) == 5


def test_unauthorized_endpoints(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 10},
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 5, "idempotency_key": "test"},
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/confirm",
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/cancel",
        headers={"X-API-Key": "invalid"}
    )
    assert response.status_code == 401
