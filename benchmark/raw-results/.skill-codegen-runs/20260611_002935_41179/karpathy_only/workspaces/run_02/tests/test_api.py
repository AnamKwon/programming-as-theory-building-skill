import pytest
from fastapi.testclient import TestClient
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService
from src.commerce_service import app as app_module

@pytest.fixture(autouse=True)
def setup_test_db():
    app_module.repo = Repository(":memory:")
    app_module.service = CommerceService(app_module.repo)
    yield
    app_module.repo.clear_all()


@pytest.fixture
def client():
    from src.commerce_service.app import app
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU-001"


def test_create_sku_no_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_adjust_stock_no_auth(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50}
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 150, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    assert response1.status_code == 201
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]


def test_create_reservation_no_auth(client):
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"}
    )
    assert response.status_code == 401


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client):
    from datetime import datetime, timezone, timedelta
    from src.commerce_service import app as app_module

    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )

    created_at = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    reservation_id = app_module.repo.create_reservation("SKU-001", 30, "key-1", created_at)
    app_module.repo.deduct_stock("SKU-001", 30)

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_confirm_reservation_invalid_state(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"}
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 400


def test_confirm_reservation_no_auth(client):
    response = client.post("/reservations/1/confirm")
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-key-123"}
    )

    from src.commerce_service import app as app_module
    available = app_module.repo.get_available_stock("SKU-001")
    assert available == 100


def test_cancel_reservation_no_auth(client):
    response = client.post("/reservations/1/cancel")
    assert response.status_code == 401


def test_get_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["orders"] == []
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 0


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 1000},
        headers={"X-API-Key": "test-key-123"}
    )
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "test-key-123"}
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key-123"}
        )

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["total"] == 25
    assert data1["page"] == 1

    response2 = client.get("/orders?page=2&size=10")
    data2 = response2.json()
    assert len(data2["orders"]) == 10

    response3 = client.get("/orders?page=3&size=10")
    data3 = response3.json()
    assert len(data3["orders"]) == 5


def test_get_orders_no_auth_required(client):
    response = client.get("/orders")
    assert response.status_code == 200


def test_workflow_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key-123"}
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"}
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key-123"}
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert data["total"] == 1
    assert data["orders"][0]["reservation_id"] == reservation_id
