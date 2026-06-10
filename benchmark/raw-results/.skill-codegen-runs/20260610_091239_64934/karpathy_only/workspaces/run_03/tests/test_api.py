import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

import commerce_service.app as app_module
from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def client():
    tmpdir = tempfile.mkdtemp()
    db_path = str(Path(tmpdir) / "test.db")
    repo = Repository(db_path=db_path)
    service = Service(repo)

    app_module._repo = repo
    app_module._service = service

    yield TestClient(app_module.app)

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def headers():
    return {"X-API-Key": "test-key-12345"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, headers):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["name"] == "Widget A"
    assert data["total_stock"] == 100
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_without_auth(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403


def test_adjust_stock(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/skus/SKU001/adjust-stock",
        json={"quantity_change": 50},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_stock"] == 150


def test_adjust_stock_nonexistent(client, headers):
    response = client.post(
        "/skus/NONEXISTENT/adjust-stock",
        json={"quantity_change": 50},
        headers=headers,
    )
    assert response.status_code == 404


def test_create_reservation(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == ReservationStatus.PENDING.value


def test_create_reservation_insufficient_stock(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 150},
        headers=headers,
    )
    assert response.status_code == 409


def test_idempotent_reservation(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )

    res1 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers=headers,
    )
    res2 = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        headers=headers,
    )

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["reservation_id"] == res2.json()["reservation_id"]


def test_confirm_reservation(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30},
        headers=headers,
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == ReservationStatus.CONFIRMED.value
    assert data["confirmed_at"] is not None


def test_cancel_reservation(client, headers):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "name": "Widget A", "total_stock": 100},
        headers=headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30},
        headers=headers,
    )
    res_id = res_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == ReservationStatus.CANCELLED.value
    assert data["cancelled_at"] is not None


def test_list_orders_empty(client, headers):
    response = client.get("/orders", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["orders"] == []
    assert data["total"] == 0
    assert data["offset"] == 0
    assert data["limit"] == 10


def test_list_orders_pagination(client, headers):
    for i in range(15):
        client.post(
            "/skus",
            json={"sku_id": f"SKU{i:03d}", "name": f"Widget {i}", "total_stock": 100},
            headers=headers,
        )

    response = client.get("/orders?offset=0&limit=5", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["offset"] == 0
    assert data["limit"] == 5


def test_operations_without_auth_fail(client):
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30},
    )
    assert response.status_code == 403

    response = client.get("/orders")
    assert response.status_code == 403

    response = client.post(
        "/skus/SKU001/adjust-stock",
        json={"quantity_change": 50},
    )
    assert response.status_code == 403
