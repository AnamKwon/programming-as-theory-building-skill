import pytest
import uuid
from fastapi.testclient import TestClient
from commerce_service import app as app_module
from commerce_service.repository import Repository
from commerce_service.service import CommercService


@pytest.fixture
def repo():
    db_name = f"memdb_{uuid.uuid4().hex[:8]}"
    return Repository(f"sqlite:///file:{db_name}?mode=memory&cache=shared&uri=true")


@pytest.fixture
def mock_service(repo):
    return CommercService(repo)


@pytest.fixture
def client(mock_service):
    app_module.app.dependency_overrides[app_module.get_service] = lambda: mock_service
    client = TestClient(app_module.app)
    yield client
    app_module.app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_unauthorized(client):
    response = client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    })
    assert response.status_code == 401


def test_create_sku_authorized(client):
    response = client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    assert response.json()["sku_id"] == "SKU001"


def test_create_sku_invalid_auth_scheme(client):
    response = client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Basic test"})
    assert response.status_code == 401


def test_create_reservation_success(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})

    response = client.post("/reservations", json={
        "sku_id": "SKU001",
        "quantity": 10,
        "idempotency_key": "idempotency-1",
        "ttl_seconds": 3600
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 5
    }, headers={"Authorization": "Bearer test-key"})

    response = client.post("/reservations", json={
        "sku_id": "SKU001",
        "quantity": 10,
        "idempotency_key": "idempotency-1",
        "ttl_seconds": 3600
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 409


def test_reservation_idempotency_via_api(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})

    payload = {
        "sku_id": "SKU001",
        "quantity": 10,
        "idempotency_key": "idempotency-1",
        "ttl_seconds": 3600
    }
    response1 = client.post("/reservations", json=payload, headers={"Authorization": "Bearer test-key"})
    response2 = client.post("/reservations", json=payload, headers={"Authorization": "Bearer test-key"})

    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})

    res_response = client.post("/reservations", json={
        "sku_id": "SKU001",
        "quantity": 10,
        "idempotency_key": "idempotency-1",
        "ttl_seconds": 3600
    }, headers={"Authorization": "Bearer test-key"})

    res_id = res_response.json()["id"]
    confirm_response = client.post(f"/reservations/{res_id}/confirm", headers={"Authorization": "Bearer test-key"})
    assert confirm_response.status_code == 200
    assert confirm_response.json()["quantity"] == 10


def test_confirm_nonexistent_reservation(client):
    response = client.post("/reservations/nonexistent/confirm", headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 404


def test_cancel_reservation(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})

    res_response = client.post("/reservations", json={
        "sku_id": "SKU001",
        "quantity": 10,
        "idempotency_key": "idempotency-1",
        "ttl_seconds": 3600
    }, headers={"Authorization": "Bearer test-key"})

    res_id = res_response.json()["id"]
    cancel_response = client.post(f"/reservations/{res_id}/cancel", headers={"Authorization": "Bearer test-key"})
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_list_orders_pagination(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})

    for i in range(5):
        res_response = client.post("/reservations", json={
            "sku_id": "SKU001",
            "quantity": 5,
            "idempotency_key": f"idempotency-{i}",
            "ttl_seconds": 3600
        }, headers={"Authorization": "Bearer test-key"})
        res_id = res_response.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers={"Authorization": "Bearer test-key"})

    response = client.get("/orders?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 2
    assert data["skip"] == 0
    assert data["limit"] == 2
    assert data["total"] >= 1


def test_list_orders_no_auth_required(client):
    response = client.get("/orders")
    assert response.status_code == 200


def test_adjust_stock(client):
    client.post("/skus", json={
        "sku_id": "SKU001",
        "name": "Product A",
        "initial_stock": 100
    }, headers={"Authorization": "Bearer test-key"})

    response = client.post("/skus/SKU001/adjust-stock", json={
        "quantity_delta": 50
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    assert response.json()["available"] == 150
