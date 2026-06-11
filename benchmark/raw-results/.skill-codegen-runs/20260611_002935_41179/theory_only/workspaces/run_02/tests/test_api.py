import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
import sqlite3
from commerce_service.app import app, repo, service
from commerce_service.repository import Repository


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        test_repo = Repository(db_path)
        test_repo.init_db()

        original_repo = repo
        repo.db_path = db_path

        yield db_path

        repo.db_path = original_repo.db_path


@pytest.fixture
def client(temp_db):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-token-12345"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, auth_headers):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_missing_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-002", "initial_stock": 50}
    )
    assert response.status_code == 403


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-003", "initial_stock": 50},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_adjust_stock_increase(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-004", "initial_stock": 50}, headers=auth_headers)

    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-004", "amount": 20},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70


def test_adjust_stock_decrease(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-005", "initial_stock": 50}, headers=auth_headers)

    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-005", "amount": -10},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 40


def test_happy_path_workflow(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-006", "initial_stock": 100}, headers=auth_headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-006", "quantity": 30, "idempotency_key": "order-001"},
        headers=auth_headers
    )
    assert res_response.status_code == 201
    reservation = res_response.json()
    assert reservation["status"] == "PENDING"
    reservation_id = reservation["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers
    )
    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["status"] == "CONFIRMED"

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] == 1
    assert len(orders_data["orders"]) == 1
    assert orders_data["orders"][0]["sku"] == "WIDGET-006"
    assert orders_data["orders"][0]["quantity"] == 30


def test_insufficient_stock(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-007", "initial_stock": 20}, headers=auth_headers)

    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-007", "quantity": 50, "idempotency_key": "order-002"},
        headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_idempotency(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-008", "initial_stock": 100}, headers=auth_headers)

    first_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-008", "quantity": 25, "idempotency_key": "idempotent-key-1"},
        headers=auth_headers
    )
    assert first_response.status_code == 201
    first_reservation = first_response.json()

    second_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-008", "quantity": 25, "idempotency_key": "idempotent-key-1"},
        headers=auth_headers
    )
    assert second_response.status_code == 201
    second_reservation = second_response.json()

    assert first_reservation["id"] == second_reservation["id"]
    assert first_reservation == second_reservation

    sku_response = client.get("/orders?page=1&size=10")
    orders_data = sku_response.json()
    assert orders_data["total"] == 0


def test_expired_reservation(client, auth_headers, monkeypatch):
    from datetime import datetime, timedelta
    import time

    client.post("/skus", json={"sku": "WIDGET-009", "initial_stock": 100}, headers=auth_headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-009", "quantity": 20, "idempotency_key": "expire-test-1"},
        headers=auth_headers
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    old_time = datetime.utcnow() - timedelta(seconds=400)
    repo.db_path = Path(repo.db_path)
    import sqlite3
    conn = sqlite3.connect(str(repo.db_path))
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time.isoformat(), reservation_id)
    )
    conn.commit()
    conn.close()

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers
    )
    assert confirm_response.status_code == 400
    assert confirm_response.json()["detail"] == "Reservation expired"

    conn = sqlite3.connect(str(repo.db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM reservations WHERE id = ?", (reservation_id,))
    status_row = cursor.fetchone()
    conn.close()
    assert status_row[0] == "EXPIRED"

    conn = sqlite3.connect(str(repo.db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT available_stock FROM skus WHERE sku = 'WIDGET-009'")
    stock_row = cursor.fetchone()
    conn.close()
    assert stock_row[0] == 100


def test_cancel_reservation(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-010", "initial_stock": 100}, headers=auth_headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-010", "quantity": 30, "idempotency_key": "cancel-test-1"},
        headers=auth_headers
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_headers
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

    conn = sqlite3.connect(str(repo.db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT available_stock FROM skus WHERE sku = 'WIDGET-010'")
    stock_row = cursor.fetchone()
    conn.close()
    assert stock_row[0] == 100


def test_confirm_non_pending_reservation(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-011", "initial_stock": 100}, headers=auth_headers)

    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-011", "quantity": 20, "idempotency_key": "state-test-1"},
        headers=auth_headers
    )
    reservation = res_response.json()
    reservation_id = reservation["id"]

    client.post(f"/reservations/{reservation_id}/confirm", headers=auth_headers)

    second_confirm = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers
    )
    assert second_confirm.status_code == 400
    assert "not in PENDING state" in second_confirm.json()["detail"]


def test_pagination(client, auth_headers):
    client.post("/skus", json={"sku": "WIDGET-012", "initial_stock": 500}, headers=auth_headers)

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "WIDGET-012", "quantity": 10, "idempotency_key": f"page-test-{i}"},
            headers=auth_headers
        )
        res_id = res_response.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)

    page1 = client.get("/orders?page=1&size=10")
    assert page1.status_code == 200
    data1 = page1.json()
    assert data1["total"] == 15
    assert data1["page"] == 1
    assert data1["size"] == 10
    assert len(data1["orders"]) == 10

    page2 = client.get("/orders?page=2&size=10")
    assert page2.status_code == 200
    data2 = page2.json()
    assert data2["total"] == 15
    assert data2["page"] == 2
    assert len(data2["orders"]) == 5


def test_unauthorized_mutation_operations(client):
    invalid_key = {"X-API-Key": "invalid"}

    response = client.post(
        "/skus",
        json={"sku": "WIDGET-013", "initial_stock": 100},
        headers=invalid_key
    )
    assert response.status_code == 401

    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-013", "amount": 10},
        headers=invalid_key
    )
    assert response.status_code == 401

    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-013", "quantity": 10, "idempotency_key": "test"},
        headers=invalid_key
    )
    assert response.status_code == 401
