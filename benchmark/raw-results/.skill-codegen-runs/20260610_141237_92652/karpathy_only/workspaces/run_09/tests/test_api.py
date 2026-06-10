import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, repository, service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    global repository, service
    from commerce_service.repository import Repository
    from commerce_service.service import CommerceService

    repository = Repository(":memory:")
    service = CommerceService(repository)
    app.dependency_overrides = {}


VALID_API_KEY = "test-api-key-12345"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_no_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_sku_duplicate(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 409


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 150


def test_adjust_stock_nonexistent_sku(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-999", "amount": 10},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert "id" in data


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 30},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response1.status_code == 201
    id1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response2.status_code == 200
    id2 = response2.json()["id"]

    assert id1 == id2

    sku_response = client.get(
        "/health"
    )
    assert sku_response.status_code == 200


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
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
    assert "order_id" in data


def test_confirm_reservation_expired(client):
    from datetime import datetime, timedelta

    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    reservation_id = res.json()["id"]

    reservation = repository.get_reservation(reservation_id)
    old_created_at = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    repository._get_connection().execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_created_at, reservation_id),
    )
    repository._get_connection().commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"

    sku = repository.get_sku("SKU-001")
    assert sku["available_stock"] == 100
    assert sku["reserved_stock"] == 0


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
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
    assert data["restored_stock"] == 100


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY},
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1

    response2 = client.get("/orders?page=2&size=10")
    data2 = response2.json()
    assert len(data2["items"]) == 10
    assert data2["page"] == 2

    response3 = client.get("/orders?page=3&size=10")
    data3 = response3.json()
    assert len(data3["items"]) == 5
    assert data3["page"] == 3


def test_unauthorized_mutation_endpoints(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 10},
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/confirm",
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations/1/cancel",
    )
    assert response.status_code == 401


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res.status_code == 201
    reservation_id = res.json()["id"]

    res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res.status_code == 200
    order_id = res.json()["order_id"]

    res = client.get("/orders?page=1&size=10")
    assert res.status_code == 200
    orders = res.json()["items"]
    assert len(orders) > 0
    assert orders[0]["id"] == order_id
    assert orders[0]["sku"] == "SKU-001"
    assert orders[0]["quantity"] == 50
