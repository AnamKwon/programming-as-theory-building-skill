import pytest
import os
from fastapi.testclient import TestClient
from commerce_service.repository import init_db, DATABASE_URL


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    yield
    if os.path.exists(DATABASE_URL) and DATABASE_URL != ":memory:":
        os.remove(DATABASE_URL)


@pytest.fixture
def client():
    from commerce_service.app import app
    return TestClient(app)


VALID_API_KEY = "test-api-key"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100
    assert data["total_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-002", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-003", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_create_sku_duplicate(client):
    client.post(
        "/skus",
        json={"sku": "SKU-004", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/skus",
        json={"sku": "SKU-004", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-005", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-005", "amount": 30},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 130


def test_adjust_stock_missing_api_key(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-006", "amount": 10}
    )
    assert response.status_code == 401


def test_adjust_stock_nonexistent_sku(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT", "amount": 10},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-007", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-007", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-007"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "idempotency-1"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-008", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-008", "quantity": 100, "idempotency_key": "idempotency-2"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_missing_api_key(client):
    response = client.post(
        "/reservations",
        json={"sku": "SKU-009", "quantity": 10, "idempotency_key": "idempotency-3"}
    )
    assert response.status_code == 401


def test_idempotency_key_returns_same_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-010", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-010", "quantity": 20, "idempotency_key": "idempotency-4"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-010", "quantity": 20, "idempotency_key": "idempotency-4"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"]


def test_idempotency_no_double_deduction(client):
    client.post(
        "/skus",
        json={"sku": "SKU-011", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    client.post(
        "/reservations",
        json={"sku": "SKU-011", "quantity": 30, "idempotency_key": "idempotency-5"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    client.post(
        "/reservations",
        json={"sku": "SKU-011", "quantity": 30, "idempotency_key": "idempotency-5"},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-011", "amount": 0},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.json()["available_stock"] == 70


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-012", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU-012", "quantity": 25, "idempotency_key": "idempotency-6"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res1.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_missing_api_key(client):
    response = client.post(
        "/reservations/1/confirm"
    )
    assert response.status_code == 401


def test_confirm_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU-013", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU-013", "quantity": 20, "idempotency_key": "idempotency-7"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res1.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]


def test_confirm_reservation_nonexistent(client):
    response = client.post(
        "/reservations/999/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-014", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU-014", "quantity": 25, "idempotency_key": "idempotency-8"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res1.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-014", "amount": 0},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert sku_response.json()["available_stock"] == 100


def test_cancel_reservation_missing_api_key(client):
    response = client.post(
        "/reservations/1/cancel"
    )
    assert response.status_code == 401


def test_cancel_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU-015", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU-015", "quantity": 20, "idempotency_key": "idempotency-9"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res1.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-016", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY}
    )

    for i in range(15):
        res1 = client.post(
            "/reservations",
            json={"sku": "SKU-016", "quantity": 10, "idempotency_key": f"idempotency-{i}"},
            headers={"X-API-Key": VALID_API_KEY}
        )
        reservation_id = res1.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY}
        )

    response1 = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 10
    assert data1["total"] == 15
    assert data1["page"] == 1
    assert data1["size"] == 10

    response2 = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 5
    assert data2["total"] == 15
    assert data2["page"] == 2


def test_get_orders_missing_api_key(client):
    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU-FINAL", "initial_stock": 200},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU-FINAL", "quantity": 50, "idempotency_key": "final-reservation"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert res1.status_code == 201
    reservation_data = res1.json()
    assert reservation_data["status"] == "PENDING"

    reservation_id = reservation_data["id"]
    res2 = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert res2.status_code == 200

    res3 = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert res3.status_code == 200
    orders_data = res3.json()
    assert len(orders_data["items"]) == 1
    assert orders_data["items"][0]["reservation_id"] == reservation_id
