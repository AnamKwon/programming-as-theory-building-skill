import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture(autouse=True)
def reset_app_state(temp_db):
    from src.commerce_service import app as app_module
    app_module.repo = Repository(db_path=temp_db)
    app_module.service = CommerceService(app_module.repo)
    yield
    del app_module.repo
    del app_module.service


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_no_auth(client):
    response = client.post("/skus", json={"sku": "SKU001", "initial_stock": 100})
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer invalid-key"}
    )
    assert response.status_code == 401


def test_create_sku_valid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_adjust_stock_valid_auth(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150


def test_adjust_stock_negative(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 70


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 30},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["quantity"] == 50
    assert data["sku"] == "SKU001"


def test_create_reservation_no_auth(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"}
    )
    assert response.status_code == 401


def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response1.json()["id"] == response2.json()["id"]
    assert response1.status_code == 201
    assert response2.status_code == 201


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert confirm_response.status_code == 200
    data = confirm_response.json()
    assert data["reservation_id"] == res_id
    assert "id" in data


def test_confirm_reservation_no_auth(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_id = res_response.json()["id"]

    response = client.post(f"/reservations/{res_id}/confirm")
    assert response.status_code == 401


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_id = res_response.json()["id"]

    cancel_response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"


def test_cancel_reservation_no_auth(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_id = res_response.json()["id"]

    response = client.post(f"/reservations/{res_id}/cancel")
    assert response.status_code == 401


def test_get_orders_no_auth_required(client):
    response = client.get("/orders")
    assert response.status_code == 200


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
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"Authorization": "Bearer test-api-key"}
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
            headers={"Authorization": "Bearer test-api-key"}
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"Authorization": "Bearer test-api-key"}
        )

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["page"] == 1
    assert data1["total"] == 15

    response2 = client.get("/orders?page=2&size=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["orders"]) == 5
    assert data2["page"] == 2
    assert data2["total"] == 15


def test_get_orders_custom_page_size(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"Authorization": "Bearer test-api-key"}
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
            headers={"Authorization": "Bearer test-api-key"}
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"Authorization": "Bearer test-api-key"}
        )

    response = client.get("/orders?page=1&size=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["size"] == 5


def test_happy_path_workflow(client):
    sku_response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert sku_response.status_code == 201

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert len(data["orders"]) == 1


def test_confirm_reservation_state_validation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"Authorization": "Bearer test-api-key"}
    )

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]


def test_cancel_reservation_state_validation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key1"},
        headers={"Authorization": "Bearer test-api-key"}
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"Authorization": "Bearer test-api-key"}
    )

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"Authorization": "Bearer test-api-key"}
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]
