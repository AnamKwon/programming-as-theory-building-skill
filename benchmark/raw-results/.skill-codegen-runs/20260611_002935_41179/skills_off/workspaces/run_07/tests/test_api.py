"""Tests for the API endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import init_db, DB_PATH


DB_PATH_TEST = DB_PATH


@pytest.fixture(autouse=True)
def setup_db():
    """Set up a clean database for each test."""
    if DB_PATH_TEST.exists():
        DB_PATH_TEST.unlink()
    init_db()
    yield
    if DB_PATH_TEST.exists():
        DB_PATH_TEST.unlink()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


VALID_API_KEY = "test-api-key"


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    """Tests for SKU endpoints."""

    def test_create_sku_success(self, client):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["available_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        """Test creating a SKU without API key."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-002", "initial_stock": 100},
        )
        assert response.status_code == 401
        assert "X-API-Key" in response.json()["detail"]

    def test_create_sku_invalid_api_key(self, client):
        """Test creating a SKU with invalid API key."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-003", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-004", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-004", "amount": 20},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU-004"
        assert data["available_stock"] == 120

    def test_adjust_stock_negative(self, client):
        """Test decreasing stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-005", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-005", "amount": -30},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 70


class TestReservationEndpoints:
    """Tests for reservation endpoints."""

    def test_create_reservation_success(self, client):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-006", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-006",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-006"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        """Test reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-007", "initial_stock": 20},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU-007",
                "quantity": 50,
                "idempotency_key": "idempotency-key-2",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_create_reservation_idempotent(self, client):
        """Test idempotent reservation creation."""
        client.post(
            "/skus",
            json={"sku": "SKU-008", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku": "SKU-008",
                "quantity": 30,
                "idempotency_key": "idempotency-key-3",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku": "SKU-008",
                "quantity": 30,
                "idempotency_key": "idempotency-key-3",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_confirm_reservation_success(self, client):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-009", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-009",
                "quantity": 30,
                "idempotency_key": "idempotency-key-4",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["reservation_id"] == reservation_id

    def test_confirm_reservation_expired(self, client):
        """Test confirming an expired reservation."""
        import sqlite3
        from datetime import datetime, timedelta

        client.post(
            "/skus",
            json={"sku": "SKU-010", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-010",
                "quantity": 30,
                "idempotency_key": "idempotency-key-5",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res_response.json()["id"]

        conn = sqlite3.connect(str(DB_PATH_TEST))
        cursor = conn.cursor()
        old_time = (
            datetime.utcnow() - timedelta(seconds=310)
        ).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation_id),
        )
        conn.commit()
        conn.close()

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Reservation expired"

    def test_confirm_non_pending_reservation(self, client):
        """Test confirming a non-PENDING reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-011", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-011",
                "quantity": 30,
                "idempotency_key": "idempotency-key-6",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert "not in PENDING status" in response.json()["detail"]

    def test_cancel_reservation_success(self, client):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-012", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-012",
                "quantity": 30,
                "idempotency_key": "idempotency-key-7",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_non_pending_reservation(self, client):
        """Test cancelling a non-PENDING reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-013", "initial_stock": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-013",
                "quantity": 30,
                "idempotency_key": "idempotency-key-8",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert "not in PENDING status" in response.json()["detail"]


class TestOrderEndpoints:
    """Tests for order endpoints."""

    def test_get_orders_empty(self, client):
        """Test getting orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["orders"] == []
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total_pages"] == 0

    def test_get_orders_pagination(self, client):
        """Test pagination of orders."""
        client.post(
            "/skus",
            json={"sku": "SKU-014", "initial_stock": 1000},
            headers={"X-API-Key": VALID_API_KEY},
        )

        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU-014",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-key-{i}",
                },
                headers={"X-API-Key": VALID_API_KEY},
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": VALID_API_KEY},
            )

        response_page1 = client.get("/orders?page=1&size=10")
        assert response_page1.status_code == 200
        data_page1 = response_page1.json()
        assert len(data_page1["orders"]) == 10
        assert data_page1["total"] == 15
        assert data_page1["page"] == 1
        assert data_page1["total_pages"] == 2

        response_page2 = client.get("/orders?page=2&size=10")
        assert response_page2.status_code == 200
        data_page2 = response_page2.json()
        assert len(data_page2["orders"]) == 5
        assert data_page2["page"] == 2
