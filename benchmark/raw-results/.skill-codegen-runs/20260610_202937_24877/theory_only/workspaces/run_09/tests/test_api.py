"""Tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from commerce_service.security import API_KEY


@pytest.fixture(scope="function", autouse=True)
def setup_db():
    """Initialize database before each test."""
    from commerce_service.repository import init_db, DATABASE_PATH

    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    init_db()
    yield


@pytest.fixture(scope="function")
def app():
    """Get the FastAPI app."""
    from commerce_service.app import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="function")
def repo():
    """Get the repository instance from the app."""
    from commerce_service.app import repository
    return repository


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def headers():
    """Return headers with valid API key."""
    return {"X-API-Key": API_KEY}


class TestHealthCheck:
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, headers):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["stock"] == 100

    def test_create_sku_unauthorized(self, client):
        """Test creating a SKU without API key."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100}
        )
        assert response.status_code == 403

    def test_create_sku_invalid_key(self, client):
        """Test creating a SKU with invalid API key."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, headers):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 50},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["previous_stock"] == 100
        assert data["new_stock"] == 150
        assert data["adjustment"] == 50

    def test_adjust_stock_nonexistent_sku(self, client, headers):
        """Test adjusting stock for non-existent SKU."""
        response = client.post(
            "/stock/adjust",
            json={"sku": "NONEXISTENT", "amount": 50},
            headers=headers
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, headers):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["quantity"] == 50
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, headers):
        """Test creating a reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 150, "idempotency_key": "key-1"},
            headers=headers
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client, headers):
        """Test idempotent reservation creation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        response1 = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        data1 = response1.json()

        response2 = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        data2 = response2.json()

        assert response2.status_code == 201
        assert data1["id"] == data2["id"]
        assert data1["created_at"] == data2["created_at"]

    def test_create_reservation_unauthorized(self, client):
        """Test creating a reservation without API key."""
        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"}
        )
        assert response.status_code == 403

    def test_confirm_reservation_success(self, client, headers):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"
        assert "order_id" in data

    def test_confirm_reservation_expired(self, client, headers, repo):
        """Test confirming an expired reservation."""
        from datetime import datetime, timedelta

        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        reservation_id = res.json()["id"]

        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        repo.set_reservation_created_at(reservation_id, old_time)

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_confirm_reservation_invalid_state(self, client, headers):
        """Test confirming a reservation that's not PENDING."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers
        )

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers
        )
        assert response.status_code == 400

    def test_confirm_reservation_not_found(self, client, headers):
        """Test confirming a non-existent reservation."""
        response = client.post(
            "/reservations/999/confirm",
            headers=headers
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client, headers):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"
        assert data["restored_stock"] == 50

    def test_cancel_reservation_invalid_state(self, client, headers):
        """Test cancelling a reservation that's not PENDING."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers
        )

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=headers
        )
        assert response.status_code == 400

    def test_cancel_reservation_not_found(self, client, headers):
        """Test cancelling a non-existent reservation."""
        response = client.post(
            "/reservations/999/cancel",
            headers=headers
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        """Test listing orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1
        assert data["size"] == 10

    def test_list_orders_with_pagination(self, client, headers):
        """Test listing orders with pagination."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku": "SKU-001", "quantity": 1, "idempotency_key": f"key-{i}"},
                headers=headers
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=headers
            )

        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1

        response = client.get("/orders?page=2&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 15
        assert data["page"] == 2

    def test_list_orders_invalid_pagination(self, client):
        """Test listing orders with invalid pagination parameters."""
        response = client.get("/orders?page=0&size=10")
        assert response.status_code == 400

        response = client.get("/orders?page=1&size=-1")
        assert response.status_code == 400

    def test_happy_path_workflow(self, client, headers):
        """Test the complete happy path workflow."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=headers
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=headers
        )
        assert res.status_code == 201
        reservation_id = res.json()["id"]

        res = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers
        )
        assert res.status_code == 200
        order_id = res.json()["order_id"]

        res = client.get("/orders")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == order_id
        assert data["items"][0]["sku"] == "SKU-001"
        assert data["items"][0]["quantity"] == 50
