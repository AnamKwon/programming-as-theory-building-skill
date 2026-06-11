"""Integration tests for commerce API."""
import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def api_token():
    """Get API token for tests."""
    return "test-token-secret"


@pytest.fixture
def auth_headers(api_token):
    """Get authorization headers."""
    return {"X-API-Key": api_token}


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    """Test SKU endpoints."""

    def test_create_sku_success(self, client, auth_headers):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU001"
        assert response.json()["available_stock"] == 100

    def test_create_sku_without_auth(self, client):
        """Test creating a SKU without authentication."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_token(self, client):
        """Test creating a SKU with invalid token."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-token"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, auth_headers):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 150

    def test_adjust_stock_negative(self, client, auth_headers):
        """Test adjusting stock with negative amount."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 70

    def test_adjust_stock_sku_not_found(self, client, auth_headers):
        """Test adjusting stock for non-existent SKU."""
        response = client.post(
            "/stock/adjust",
            json={"sku": "UNKNOWN", "amount": 50},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    """Test reservation endpoints."""

    @pytest.fixture
    def setup_sku(self, client, auth_headers):
        """Create a test SKU."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )

    def test_create_reservation_success(self, client, auth_headers, setup_sku):
        """Test successful reservation creation."""
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU001"
        assert response.json()["quantity"] == 50
        assert response.json()["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, auth_headers, setup_sku):
        """Test reservation with insufficient stock."""
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 150,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_idempotent_reservation(self, client, auth_headers, setup_sku):
        """Test idempotent reservation creation."""
        # First request
        response1 = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        assert response1.status_code == 201
        reservation_id = response1.json()["id"]

        # Second request with same idempotency key
        response2 = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        assert response2.status_code == 201
        assert response2.json()["id"] == reservation_id

    def test_confirm_reservation_success(self, client, auth_headers, setup_sku):
        """Test successful reservation confirmation."""
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["reservation_id"] == reservation_id

    def test_confirm_reservation_expired(self, client, auth_headers, setup_sku):
        """Test confirming an expired reservation."""
        from datetime import datetime, timedelta
        from src.commerce_service.app import service

        # Create reservation
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        reservation_id = res.json()["id"]

        # Manually expire the reservation
        conn = service.db.get_connection()
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservation SET created_at = ? WHERE id = ?",
            (old_time, reservation_id),
        )
        conn.commit()

        # Try to confirm
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Reservation expired" in response.json()["detail"]

    def test_cancel_reservation_success(self, client, auth_headers, setup_sku):
        """Test successful reservation cancellation."""
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_confirm_non_pending_reservation(self, client, auth_headers, setup_sku):
        """Test confirming a non-pending reservation."""
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        reservation_id = res.json()["id"]

        # Confirm once
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )

        # Try to confirm again
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_cancel_non_pending_reservation(self, client, auth_headers, setup_sku):
        """Test canceling a non-pending reservation."""
        res = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        reservation_id = res.json()["id"]

        # Confirm the reservation
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )

        # Try to cancel
        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestOrderEndpoints:
    """Test order endpoints."""

    @pytest.fixture
    def setup_orders(self, client, auth_headers):
        """Create test orders."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers=auth_headers,
        )

        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku": "SKU001",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-{i}",
                },
                headers=auth_headers,
            )
            client.post(
                f"/reservations/{res.json()['id']}/confirm",
                headers=auth_headers,
            )

    def test_get_orders_default_pagination(self, client, auth_headers, setup_orders):
        """Test getting orders with default pagination."""
        response = client.get("/orders", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["size"] == 10

    def test_get_orders_custom_pagination(self, client, auth_headers, setup_orders):
        """Test getting orders with custom pagination."""
        response = client.get("/orders?page=2&size=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["total"] == 15
        assert data["page"] == 2
        assert data["size"] == 5

    def test_get_orders_last_page(self, client, auth_headers, setup_orders):
        """Test getting the last page of orders."""
        response = client.get("/orders?page=2&size=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["total"] == 15

    def test_get_orders_without_auth(self, client):
        """Test getting orders without authentication."""
        response = client.get("/orders")
        assert response.status_code == 401

    def test_get_orders_empty(self, client, auth_headers):
        """Test getting orders when none exist."""
        response = client.get("/orders", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 0
        assert data["total"] == 0


class TestEndToEndWorkflow:
    """Test complete happy path workflow."""

    def test_happy_path(self, client, auth_headers):
        """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
        # 1. Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )
        assert sku_response.status_code == 201

        # 2. Create reservation
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers=auth_headers,
        )
        assert res_response.status_code == 201
        reservation_id = res_response.json()["id"]

        # 3. Confirm reservation
        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )
        assert confirm_response.status_code == 200
        order_id = confirm_response.json()["id"]

        # 4. Get orders
        orders_response = client.get("/orders", headers=auth_headers)
        assert orders_response.status_code == 200
        data = orders_response.json()
        assert len(data["orders"]) > 0

        # Verify the order exists
        order_ids = [order["id"] for order in data["orders"]]
        assert order_id in order_ids
