import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, _service, _repo
from commerce_service.security import VALID_API_KEY


@pytest.fixture(autouse=True)
def reset_db():
    global _repo
    from commerce_service.repository import Repository
    from commerce_service.service import CommerceService
    app.dependency_overrides = {}

    new_repo = Repository(":memory:")
    new_service = CommerceService(new_repo)

    import commerce_service.app as app_module
    app_module._repo = new_repo
    app_module._service = new_service

    yield

    app.dependency_overrides = {}


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -20},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 80


def test_adjust_stock_unauthorized(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -20}
    )
    assert response.status_code == 401


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"
    assert response.json()["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 100,
            "idempotency_key": "idempotency-1"
        }
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    first_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    first_id = first_response.json()["id"]

    second_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    second_id = second_response.json()["id"]

    assert first_id == second_id
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    sku_response = client.get("/orders")
    assert sku_response.status_code == 200


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    reservation_id = res_response.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 200
    assert response.json()["reservation_id"] == reservation_id


def test_confirm_reservation_invalid_state(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    reservation_id = res_response.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm")

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 400


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    reservation_id = res_response.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_invalid_state(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 20,
            "idempotency_key": "idempotency-1"
        }
    )
    reservation_id = res_response.json()["id"]

    client.post(f"/reservations/{reservation_id}/confirm")

    response = client.post(f"/reservations/{reservation_id}/cancel")
    assert response.status_code == 400


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 150},
        headers={"X-API-Key": VALID_API_KEY}
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 1,
                "idempotency_key": f"idempotency-{i}"
            }
        )
        reservation_id = res_response.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm")

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["size"] == 10

    response_page2 = client.get("/orders?page=2&size=10")
    data_page2 = response_page2.json()
    assert len(data_page2["items"]) == 5
    assert data_page2["total"] == 15


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "PRODUCT-123", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "PRODUCT-123",
            "quantity": 5,
            "idempotency_key": "order-abc-123"
        }
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(f"/reservations/{reservation_id}/confirm")
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert orders["total"] == 1
    assert orders["items"][0]["id"] == order_id


def test_reservation_expiry(client):
    import commerce_service.app as app_module
    from datetime import datetime, timezone, timedelta

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    repo = app_module._repo
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()

    conn = repo._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at) VALUES (?, ?, ?, ?, ?)",
        ("SKU001", 20, "idempotency-key-1", "PENDING", old_time)
    )
    conn.commit()
    res_id = cursor.lastrowid
    conn.close()

    repo.deduct_stock("SKU001", 20)

    response = client.post(f"/reservations/{res_id}/confirm")
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"

    sku = repo.get_sku("SKU001")
    assert sku['available_stock'] == 100
