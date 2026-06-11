import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from src.commerce_service.app import app
from src.commerce_service.repository import Database
from src.commerce_service.service import CommerceService


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    db.initialize_schema()
    yield db
    os.unlink(path)


@pytest.fixture
def client(test_db):
    # Replace the app's database with test database
    from src.commerce_service import app as app_module

    app_module.db = test_db
    app_module.service = CommerceService(test_db)
    return TestClient(app)


@pytest.fixture
def valid_token():
    return "sk-test-key-123"


@pytest.fixture
def auth_header(valid_token):
    return {"Authorization": f"Bearer {valid_token}"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, auth_header):
    response = client.post(
        "/skus",
        json={"sku": "TEST-001", "initial_stock": 100},
        headers=auth_header,
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "TEST-001"


def test_create_sku_missing_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "TEST-001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_token(client):
    response = client.post(
        "/skus",
        json={"sku": "TEST-001", "initial_stock": 100},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_adjust_stock(client, auth_header):
    # Create SKU first
    client.post(
        "/skus",
        json={"sku": "TEST-002", "initial_stock": 100},
        headers=auth_header,
    )

    # Adjust stock
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-002", "amount": 50},
        headers=auth_header,
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_adjust_stock_negative(client, auth_header):
    # Create SKU first
    client.post(
        "/skus",
        json={"sku": "TEST-003", "initial_stock": 100},
        headers=auth_header,
    )

    # Adjust stock with negative amount
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-003", "amount": -30},
        headers=auth_header,
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 70


def test_create_reservation_success(client, auth_header):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-004", "initial_stock": 100},
        headers=auth_header,
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={"sku": "TEST-004", "quantity": 10, "idempotency_key": "idem-001"},
        headers=auth_header,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-004"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, auth_header):
    # Create SKU with limited stock
    client.post(
        "/skus",
        json={"sku": "TEST-005", "initial_stock": 5},
        headers=auth_header,
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={"sku": "TEST-005", "quantity": 10, "idempotency_key": "idem-002"},
        headers=auth_header,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent(client, auth_header):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-006", "initial_stock": 100},
        headers=auth_header,
    )

    # Create first reservation
    response1 = client.post(
        "/reservations",
        json={"sku": "TEST-006", "quantity": 20, "idempotency_key": "idem-003"},
        headers=auth_header,
    )
    assert response1.status_code == 201
    data1 = response1.json()

    # Create second reservation with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku": "TEST-006", "quantity": 20, "idempotency_key": "idem-003"},
        headers=auth_header,
    )
    assert response2.status_code == 201
    data2 = response2.json()

    # Should return same reservation without deducting stock again
    assert data1["id"] == data2["id"]
    assert data1["created_at"] == data2["created_at"]

    # Verify stock was only deducted once
    response3 = client.post(
        "/stock/adjust",
        json={"sku": "TEST-006", "amount": 0},
        headers=auth_header,
    )
    # available_stock should be 80 (100 - 20 from one reservation)
    assert response3.json()["available_stock"] == 80


def test_confirm_reservation(client, auth_header):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-007", "initial_stock": 100},
        headers=auth_header,
    )

    # Create reservation
    res = client.post(
        "/reservations",
        json={"sku": "TEST-007", "quantity": 15, "idempotency_key": "idem-004"},
        headers=auth_header,
    )
    reservation_id = res.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_header,
    )
    assert response.status_code == 200
    assert response.json()["id"]
    assert "reservation_id" in response.json()


def test_confirm_reservation_expired(client, auth_header, test_db):
    import time
    from datetime import datetime, timezone, timedelta
    from src.commerce_service.repository import Database
    import sqlite3

    # Get the test database connection details from the fixture
    db_path = test_db.db_path

    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-008", "initial_stock": 100},
        headers=auth_header,
    )

    # Create reservation
    res = client.post(
        "/reservations",
        json={"sku": "TEST-008", "quantity": 25, "idempotency_key": "idem-005"},
        headers=auth_header,
    )
    reservation_id = res.json()["id"]

    # Manually backdate the reservation created_at to trigger expiration
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    # Try to confirm (should fail due to expiration)
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_header,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_confirm_reservation_not_pending(client, auth_header):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-009", "initial_stock": 100},
        headers=auth_header,
    )

    # Create and confirm a reservation
    res = client.post(
        "/reservations",
        json={"sku": "TEST-009", "quantity": 10, "idempotency_key": "idem-006"},
        headers=auth_header,
    )
    reservation_id = res.json()["id"]

    # First confirm (should succeed)
    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_header,
    )

    # Try to confirm again (should fail - not PENDING)
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_header,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation is not PENDING"


def test_cancel_reservation(client, auth_header):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-010", "initial_stock": 100},
        headers=auth_header,
    )

    # Create reservation
    res = client.post(
        "/reservations",
        json={"sku": "TEST-010", "quantity": 30, "idempotency_key": "idem-007"},
        headers=auth_header,
    )
    reservation_id = res.json()["id"]

    # Cancel reservation
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_header,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    # Verify stock was restored
    stock_check = client.post(
        "/stock/adjust",
        json={"sku": "TEST-010", "amount": 0},
        headers=auth_header,
    )
    # available_stock should be back to 100
    assert stock_check.json()["available_stock"] == 100


def test_get_orders_pagination(client, auth_header):
    # Create SKU
    client.post(
        "/skus",
        json={"sku": "TEST-011", "initial_stock": 1000},
        headers=auth_header,
    )

    # Create and confirm multiple reservations
    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "sku": "TEST-011",
                "quantity": 5,
                "idempotency_key": f"idem-order-{i}",
            },
            headers=auth_header,
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_header,
        )

    # Get first page (default size 10)
    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 15

    # Get second page
    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["page"] == 2


def test_get_orders_no_auth_required(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert "orders" in data
    assert data["page"] == 1
    assert data["size"] == 10
