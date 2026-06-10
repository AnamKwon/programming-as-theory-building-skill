import pytest
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import init_db


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_commerce.db"

    import commerce_service.repository as repo_module
    original_path = repo_module.DB_PATH
    repo_module.DB_PATH = db_path

    init_db()
    yield db_path

    repo_module.DB_PATH = original_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client(temp_db):
    return TestClient(app)


@pytest.fixture
def valid_api_key():
    return "test-key-secret"


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, valid_api_key):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 401
        assert "API key" in response.json()["detail"].lower()

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_create_duplicate_sku(self, client, valid_api_key):
        response1 = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )
        assert response1.status_code == 201

        response2 = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 50},
            headers={"X-API-Key": valid_api_key},
        )
        assert response2.status_code == 400

    def test_adjust_stock_success(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 150

    def test_adjust_stock_negative(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 70


class TestReservationEndpoints:
    def test_happy_path_workflow(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        reserve_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        assert reserve_response.status_code == 201
        reservation = reserve_response.json()
        assert reservation["status"] == "PENDING"
        assert reservation["quantity"] == 30
        reservation_id = reservation["id"]

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": valid_api_key},
        )
        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()
        assert confirmed["status"] == "CONFIRMED"

        orders_response = client.get(
            "/orders?page=1&size=10",
            headers={"X-API-Key": valid_api_key},
        )
        assert orders_response.status_code == 200
        orders_data = orders_response.json()
        assert orders_data["total"] == 1
        assert len(orders_data["orders"]) == 1

    def test_create_reservation_insufficient_stock(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 150, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_create_reservation_idempotency(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response1 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        assert response1.status_code == 201
        reservation1 = response1.json()

        response2 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        assert response2.status_code == 201
        reservation2 = response2.json()

        assert reservation1["id"] == reservation2["id"]
        assert reservation1["sku"] == reservation2["sku"]
        assert reservation1["quantity"] == reservation2["quantity"]

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        )
        assert response.status_code == 401

    def test_confirm_nonexistent_reservation(self, client, valid_api_key):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 404

    def test_confirm_expired_reservation(self, client, valid_api_key, temp_db):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 201
        reservation_id = response.json()["id"]

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=400)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation_id),
        )
        conn.commit()
        conn.close()

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": valid_api_key},
        )
        assert confirm_response.status_code == 400
        assert confirm_response.json()["detail"] == "Reservation expired"

    def test_confirm_already_confirmed_reservation(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        reservation_id = response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": valid_api_key},
        )

        response2 = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": valid_api_key},
        )
        assert response2.status_code == 400
        assert "not in PENDING state" in response2.json()["detail"]

    def test_cancel_reservation_success(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": valid_api_key},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"X-API-Key": valid_api_key},
        )
        reservation_id = response.json()["id"]

        cancel_response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": valid_api_key},
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "CANCELLED"

    def test_cancel_nonexistent_reservation(self, client, valid_api_key):
        response = client.post(
            "/reservations/999/cancel",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_list_orders_empty(self, client, valid_api_key):
        response = client.get(
            "/orders?page=1&size=10",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 0
        assert data["orders"] == []

    def test_list_orders_pagination(self, client, valid_api_key):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers={"X-API-Key": valid_api_key},
        )

        for i in range(25):
            response = client.post(
                "/reservations",
                json={
                    "sku": "SKU001",
                    "quantity": 10,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": valid_api_key},
            )
            reservation_id = response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": valid_api_key},
            )

        response1 = client.get(
            "/orders?page=1&size=10",
            headers={"X-API-Key": valid_api_key},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["page"] == 1
        assert len(data1["orders"]) == 10
        assert data1["total"] == 25

        response2 = client.get(
            "/orders?page=2&size=10",
            headers={"X-API-Key": valid_api_key},
        )
        data2 = response2.json()
        assert data2["page"] == 2
        assert len(data2["orders"]) == 10

        response3 = client.get(
            "/orders?page=3&size=10",
            headers={"X-API-Key": valid_api_key},
        )
        data3 = response3.json()
        assert data3["page"] == 3
        assert len(data3["orders"]) == 5

    def test_list_orders_missing_api_key(self, client):
        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 401
