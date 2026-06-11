import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_service():
    repository = Repository()
    service = CommerceService(repository)
    app.state.service = service


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"
    assert response.json()["initial_stock"] == 100


def test_create_sku_no_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_adjust_stock_no_auth(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
    )
    assert response.status_code == 403


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    assert response.json()["quantity"] == 50
    assert response.json()["sku"] == "SKU001"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 30},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


def test_create_reservation_no_auth(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
    )
    assert response.status_code == 403


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert response.json()["reservation_id"] == reservation_id
    assert "id" in response.json()


def test_confirm_reservation_expired(client):
    from datetime import datetime, timedelta

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    service = app.state.service
    repo = service.repo
    old_time = (datetime.utcnow() - timedelta(seconds=400)).isoformat()
    cursor = repo.conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    repo.conn.commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_confirm_reservation_not_pending(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    service = app.state.service
    repo = service.repo
    stock_before_cancel = repo.get_sku_stock("SKU001")

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"},
    )

    stock_after_cancel = repo.get_sku_stock("SKU001")
    assert stock_after_cancel == stock_before_cancel + 50


def test_cancel_reservation_no_auth(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel")
    assert response.status_code == 403


def test_get_orders_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res1.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )

    response = client.get(
        "/orders",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["orders"]) == 1


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": "test-api-key"},
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"idempotency-{i}"},
            headers={"X-API-Key": "test-api-key"},
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-api-key"},
        )

    page1 = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": "test-api-key"},
    )
    page2 = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": "test-api-key"},
    )
    page3 = client.get(
        "/orders?page=3&size=10",
        headers={"X-API-Key": "test-api-key"},
    )

    assert page1.status_code == 200
    assert page2.status_code == 200
    assert page3.status_code == 200

    assert len(page1.json()["orders"]) == 10
    assert len(page2.json()["orders"]) == 10
    assert len(page3.json()["orders"]) == 5

    assert page1.json()["total"] == 25
    assert page2.json()["total"] == 25
    assert page3.json()["total"] == 25


def test_get_orders_no_auth(client):
    response = client.get("/orders")
    assert response.status_code == 403


def test_happy_path_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )

    res_reservation = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res_reservation.status_code == 201
    reservation_id = res_reservation.json()["id"]

    res_confirm = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert res_confirm.status_code == 200
    order_id = res_confirm.json()["id"]

    res_orders = client.get(
        "/orders",
        headers={"X-API-Key": "test-api-key"},
    )
    assert res_orders.status_code == 200
    assert res_orders.json()["total"] == 1
    assert res_orders.json()["orders"][0]["id"] == order_id
