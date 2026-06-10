import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from src.commerce_service.app import app, repository, service
from src.commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def test_repo(temp_db):
    return Repository(f"sqlite:///{temp_db}")


@pytest.fixture
def client(test_repo, monkeypatch):
    monkeypatch.setattr(app, "repository", test_repo)
    from src.commerce_service.app import CommerceService
    monkeypatch.setattr(app, "service", CommerceService(test_repo))
    return TestClient(app)


API_KEY = "test-key-123"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "PRODUCT-001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
    )
    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "PRODUCT-001", "amount": -10},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "PRODUCT-001"
    assert data["available_stock"] == 90


def test_adjust_stock_requires_auth(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "PRODUCT-001", "amount": -10},
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "PRODUCT-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 30},
        headers={"X-API-Key": API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation"]["status"] == "CONFIRMED"
    assert data["order"]["sku"] == "PRODUCT-001"


def test_confirm_reservation_expired(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    reservation_model = app.service.repo.get_reservation(res_id)
    past_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    reservation_model.created_at = past_time
    session = app.service.repo.get_session()
    try:
        session.merge(reservation_model)
        session.commit()
    finally:
        session.close()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]

    updated_res = app.service.repo.get_reservation(res_id)
    assert updated_res.status == "EXPIRED"


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_requires_auth(client):
    response = client.post("/reservations/1/cancel")
    assert response.status_code == 401


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "PRODUCT-001", "quantity": 1, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    response1 = client.get("/orders?page=1&size=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 10
    assert data1["total"] == 25

    response2 = client.get("/orders?page=2&size=10")
    data2 = response2.json()
    assert len(data2["items"]) == 10

    response3 = client.get("/orders?page=3&size=10")
    data3 = response3.json()
    assert len(data3["items"]) == 5


def test_unauthorized_mutation_blocks_sku(client):
    response = client.post(
        "/skus",
        json={"sku": "PRODUCT-001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_unauthorized_mutation_blocks_reservation(client):
    response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-001", "quantity": 50, "idempotency_key": "key-1"},
    )
    assert response.status_code == 401


def test_happy_path_workflow(client):
    sku_response = client.post(
        "/skus",
        json={"sku": "PRODUCT-123", "initial_stock": 1000},
        headers={"X-API-Key": API_KEY},
    )
    assert sku_response.status_code == 201

    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-123", "quantity": 100, "idempotency_key": "order-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert confirm_response.status_code == 200

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert orders["total"] == 1
    assert orders["items"][0]["sku"] == "PRODUCT-123"
