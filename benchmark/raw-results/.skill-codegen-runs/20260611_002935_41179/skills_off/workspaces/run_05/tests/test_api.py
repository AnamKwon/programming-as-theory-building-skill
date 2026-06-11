import pytest
from datetime import datetime, timedelta


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["stock"] == 100


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_create_sku_missing_header(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 10},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["new_stock"] == 110


def test_adjust_stock_negative(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -30},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_stock"] == 70


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "idempotency-1"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 5},
        headers={"X-API-Key": "test-api-key"}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response1.status_code == 201
    data1 = response1.json()
    reservation_id = data1["id"]

    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["id"] == reservation_id
    assert data2 == data1


def test_confirm_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )
    assert confirm_response.status_code == 200
    data = confirm_response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client, db):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    from commerce_service.repository import Reservation
    old_time = datetime.utcnow() - timedelta(seconds=301)
    db.query(Reservation).filter(Reservation.id == reservation_id).update({Reservation.created_at: old_time})
    db.commit()

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )
    assert confirm_response.status_code == 400
    assert confirm_response.json()["detail"] == "Reservation expired"

    updated = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    assert updated.status == "EXPIRED"


def test_confirm_reservation_not_pending(client, db):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )
    assert confirm_response.status_code == 400


def test_cancel_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 10,
            "idempotency_key": "idempotency-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"}
    )
    assert cancel_response.status_code == 200
    data = cancel_response.json()
    assert data["status"] == "CANCELLED"

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": 0},
        headers={"X-API-Key": "test-api-key"}
    )
    assert sku_response.json()["new_stock"] == 100


def test_unauthorized_mutation_block(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 1000},
        headers={"X-API-Key": "test-api-key"}
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"key-{i}"
            },
            headers={"X-API-Key": "test-api-key"}
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-api-key"}
        )

    response_page1 = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response_page1.status_code == 200
    data1 = response_page1.json()
    assert len(data1["data"]) == 10
    assert data1["meta"]["total"] == 25
    assert data1["meta"]["page"] == 1
    assert data1["meta"]["size"] == 10
    assert data1["meta"]["total_pages"] == 3

    response_page2 = client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response_page2.status_code == 200
    data2 = response_page2.json()
    assert len(data2["data"]) == 10

    response_page3 = client.get(
        "/orders?page=3&size=10",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response_page3.status_code == 200
    data3 = response_page3.json()
    assert len(data3["data"]) == 5


def test_get_orders_default_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 1,
            "idempotency_key": "key-1"
        },
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )

    response = client.get(
        "/orders",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 1
    assert data["meta"]["size"] == 10
