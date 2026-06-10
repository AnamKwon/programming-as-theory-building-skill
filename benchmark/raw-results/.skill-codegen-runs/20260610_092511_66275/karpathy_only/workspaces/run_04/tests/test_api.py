"""Tests for the commerce service API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_service.app import app, get_service
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        yield db_path


@pytest.fixture
def service(temp_db):
    """Create a service with a temporary database."""
    repo = Repository(db_path=temp_db)
    return CommerceService(repo)


@pytest.fixture
def client(service):
    """Create a test client with dependency override."""
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    """Tests for SKU management endpoints."""

    def test_create_sku_success(self, client):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU-001"
        assert data["stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        """Test creating a SKU without API key fails."""
        response = client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_adjust_stock_success(self, client):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/skus/SKU-001/adjust-stock",
            json={"delta": 25},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 125

    def test_adjust_stock_nonexistent_sku(self, client):
        """Test adjusting stock for non-existent SKU."""
        response = client.post(
            "/skus/SKU-NONE/adjust-stock",
            json={"delta": 10},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    """Tests for reservation endpoints."""

    def test_create_reservation_success(self, client):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["quantity"] == 30

    def test_create_reservation_insufficient_stock(self, client):
        """Test creating a reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 20},
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent(self, client):
        """Test that reservations with same idempotency key are idempotent."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res1 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        res2 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 50,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert res1.json()["reservation_id"] == res2.json()["reservation_id"]
        assert res1.json()["quantity"] == res2.json()["quantity"]

    def test_confirm_reservation_success(self, client):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        reservation_id = res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reservation"]["status"] == "confirmed"
        assert data["order"]["status"] == "completed"

    def test_cancel_reservation_success(self, client):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        reservation_id = res.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrderEndpoints:
    """Tests for order endpoints."""

    def test_list_orders_empty(self, client):
        """Test listing orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0

    def test_list_orders_with_pagination(self, client):
        """Test listing orders with pagination."""
        client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        # Create and confirm 15 orders
        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku_id": "SKU-001",
                    "quantity": 1,
                    "idempotency_key": f"idempotency-{i}",
                },
                headers={"X-API-Key": "test-key"},
            )
            reservation_id = res.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": "test-key"},
            )

        # Test first page
        response = client.get("/orders?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["limit"] == 10
        assert data["offset"] == 0

        # Test second page
        response = client.get("/orders?limit=10&offset=10")
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["total"] == 15

    def test_list_orders_limit_validation(self, client):
        """Test that limit is validated and clamped."""
        response = client.get("/orders?limit=200&offset=0")
        assert response.status_code == 422  # Validation error

    def test_unauthorized_mutation(self, client):
        """Test that mutations without API key fail."""
        response = client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_integration_workflow(self, client):
        """Test a complete workflow: create SKU → reserve → confirm → lookup."""
        # Create SKU
        sku_res = client.post(
            "/skus",
            json={"sku_id": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert sku_res.status_code == 201

        # Create reservation
        res_res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU-001",
                "quantity": 30,
                "idempotency_key": "idempotency-1",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert res_res.status_code == 201
        reservation_id = res_res.json()["reservation_id"]

        # Confirm reservation
        confirm_res = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )
        assert confirm_res.status_code == 200
        order_id = confirm_res.json()["order"]["order_id"]

        # List orders
        list_res = client.get("/orders")
        assert list_res.status_code == 200
        orders = list_res.json()["orders"]
        assert len(orders) == 1
        assert orders[0]["order_id"] == order_id
        assert orders[0]["quantity"] == 30
