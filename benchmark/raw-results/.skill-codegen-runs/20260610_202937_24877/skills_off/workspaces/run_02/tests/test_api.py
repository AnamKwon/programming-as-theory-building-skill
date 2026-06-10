import pytest
import os
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from src.commerce_service.app import app
from src.commerce_service.repository import init_db, get_db_connection, DB_PATH


API_KEY = "test-token"
INVALID_KEY = "invalid-key"


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and cleanup for each test."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_no_auth(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoint:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "ABC123"
        assert data["stock"] == 100

    def test_create_sku_no_auth(self, client):
        response = client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100}
        )
        assert response.status_code == 401

    def test_create_sku_invalid_auth(self, client):
        response = client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": INVALID_KEY}
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "ABC123", "amount": 50},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stock"] == 150


class TestReservationEndpoint:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "ABC123"
        assert data["quantity"] == 10
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 50},
            headers={"X-API-Key": API_KEY}
        )
        response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 100, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_create_reservation_no_auth(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"}
        )
        assert response.status_code == 401

    def test_create_reservation_idempotent_retry(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        response1 = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        response2 = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        assert response1.status_code == 201
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        assert data1["id"] == data2["id"]

    def test_idempotent_no_double_stock_deduction(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        # Make a different reservation to check stock
        response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 91, "idempotency_key": "key-2"},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"

    def test_confirm_expired_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        res_id = res_response.json()["id"]

        # Manually update the created_at to be older than TTL
        conn = get_db_connection()
        cursor = conn.cursor()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res_id)
        )
        conn.commit()
        conn.close()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 400
        assert "Reservation expired" in response.json()["detail"]

    def test_expired_reservation_restores_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        res_id = res_response.json()["id"]

        # Manually update the created_at to be older than TTL
        conn = get_db_connection()
        cursor = conn.cursor()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res_id)
        )
        conn.commit()
        conn.close()

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY}
        )

        # Try to reserve again - should succeed if stock was restored
        response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-2"},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 201

    def test_confirm_non_pending_reservation_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY}
        )

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 400

    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-1"},
            headers={"X-API-Key": API_KEY}
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": API_KEY}
        )

        # Try to reserve the same amount again
        response = client.post(
            "/reservations",
            json={"sku": "ABC123", "quantity": 10, "idempotency_key": "key-2"},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 201


class TestOrderEndpoint:
    def test_get_orders_no_auth(self, client):
        response = client.get("/orders")
        assert response.status_code == 401

    def test_get_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )

        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={"sku": "ABC123", "quantity": 1, "idempotency_key": f"key-{i}"},
                headers={"X-API-Key": API_KEY}
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": API_KEY}
            )

        response = client.get(
            "/orders?page=1&size=10",
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 25

        response = client.get(
            "/orders?page=2&size=10",
            headers={"X-API-Key": API_KEY}
        )
        data = response.json()
        assert len(data["items"]) == 10

        response = client.get(
            "/orders?page=3&size=10",
            headers={"X-API-Key": API_KEY}
        )
        data = response.json()
        assert len(data["items"]) == 5

    def test_get_orders_default_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "ABC123", "initial_stock": 100},
            headers={"X-API-Key": API_KEY}
        )

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={"sku": "ABC123", "quantity": 1, "idempotency_key": f"key-{i}"},
                headers={"X-API-Key": API_KEY}
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": API_KEY}
            )

        response = client.get(
            "/orders",
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 15
