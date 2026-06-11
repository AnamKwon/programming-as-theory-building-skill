import pytest
import os
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Change to src directory for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture(scope="function")
def test_db():
    """Create a test database"""
    db_path = "test_commerce.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client with test database"""
    with patch("commerce_service.app.db_path", test_db):
        test_repo = Repository(test_db)
        test_service = Service(test_repo)

        # Replace global instances in the app
        import commerce_service.app as app_module
        app_module.repo = test_repo
        app_module.service = test_service

        client = TestClient(app)
        yield client


def get_headers():
    return {"X-API-Key": "your-secret-api-key"}


class TestHealthCheck:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUManagement:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=get_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["available_stock"] == 100
        assert "id" in data

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 401
        assert "API Key" in response.json()["detail"]

    def test_create_sku_invalid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401


class TestStockAdjustment:
    def test_adjust_stock_increase(self, client):
        # Create SKU first
        client.post(
            "/skus",
            json={"sku": "SKU002", "initial_stock": 50},
            headers=get_headers(),
        )

        # Adjust stock
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU002", "amount": 25},
            headers=get_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU002"
        assert data["available_stock"] == 75

    def test_adjust_stock_decrease(self, client):
        # Create SKU first
        client.post(
            "/skus",
            json={"sku": "SKU003", "initial_stock": 100},
            headers=get_headers(),
        )

        # Decrease stock
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU003", "amount": -30},
            headers=get_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 70

    def test_adjust_stock_sku_not_found(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku": "NONEXISTENT", "amount": 10},
            headers=get_headers(),
        )
        assert response.status_code == 400


class TestReservations:
    def test_create_reservation(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU004", "initial_stock": 100},
            headers=get_headers(),
        )

        # Create reservation
        response = client.post(
            "/reservations",
            json={"sku": "SKU004", "quantity": 50, "idempotency_key": "key1"},
            headers=get_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU004"
        assert data["quantity"] == 50
        assert data["status"] == "PENDING"
        assert "id" in data
        assert "created_at" in data

    def test_insufficient_stock(self, client):
        # Create SKU with low stock
        client.post(
            "/skus",
            json={"sku": "SKU005", "initial_stock": 10},
            headers=get_headers(),
        )

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={"sku": "SKU005", "quantity": 50, "idempotency_key": "key2"},
            headers=get_headers(),
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_idempotency(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU006", "initial_stock": 100},
            headers=get_headers(),
        )

        # Create reservation
        response1 = client.post(
            "/reservations",
            json={"sku": "SKU006", "quantity": 30, "idempotency_key": "key3"},
            headers=get_headers(),
        )
        assert response1.status_code == 201
        data1 = response1.json()

        # Retry with same idempotency key
        response2 = client.post(
            "/reservations",
            json={"sku": "SKU006", "quantity": 30, "idempotency_key": "key3"},
            headers=get_headers(),
        )
        assert response2.status_code == 201
        data2 = response2.json()

        # Should return same data
        assert data1["id"] == data2["id"]
        assert data1["status"] == data2["status"]
        assert data1["quantity"] == data2["quantity"]

    def test_idempotency_no_double_deduction(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU007", "initial_stock": 100},
            headers=get_headers(),
        )

        # First reservation
        client.post(
            "/reservations",
            json={"sku": "SKU007", "quantity": 50, "idempotency_key": "key4"},
            headers=get_headers(),
        )

        # Retry - should not deduct stock again
        client.post(
            "/reservations",
            json={"sku": "SKU007", "quantity": 50, "idempotency_key": "key4"},
            headers=get_headers(),
        )

        # Stock should only be deducted once
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU007", "amount": 0},
            headers=get_headers(),
        )
        assert response.json()["available_stock"] == 50


class TestConfirmReservation:
    def test_confirm_reservation(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU008", "initial_stock": 100},
            headers=get_headers(),
        )

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU008", "quantity": 50, "idempotency_key": "key5"},
            headers=get_headers(),
        )
        res_id = res_response.json()["id"]

        # Confirm reservation
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=get_headers(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_confirm_non_pending_reservation(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU009", "initial_stock": 100},
            headers=get_headers(),
        )

        # Create and confirm reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU009", "quantity": 50, "idempotency_key": "key6"},
            headers=get_headers(),
        )
        res_id = res_response.json()["id"]

        client.post(f"/reservations/{res_id}/confirm", headers=get_headers())

        # Try to confirm again
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=get_headers(),
        )
        assert response.status_code == 400
        assert "PENDING" in response.json()["detail"]


class TestCancelReservation:
    def test_cancel_reservation(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU010", "initial_stock": 100},
            headers=get_headers(),
        )

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU010", "quantity": 50, "idempotency_key": "key7"},
            headers=get_headers(),
        )
        res_id = res_response.json()["id"]

        # Cancel reservation
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=get_headers(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        # Verify stock was restored
        stock_response = client.post(
            "/stock/adjust",
            json={"sku": "SKU010", "amount": 0},
            headers=get_headers(),
        )
        assert stock_response.json()["available_stock"] == 100

    def test_cancel_non_pending_reservation(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU011", "initial_stock": 100},
            headers=get_headers(),
        )

        # Create and confirm reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU011", "quantity": 50, "idempotency_key": "key8"},
            headers=get_headers(),
        )
        res_id = res_response.json()["id"]

        client.post(f"/reservations/{res_id}/confirm", headers=get_headers())

        # Try to cancel confirmed reservation
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=get_headers(),
        )
        assert response.status_code == 400


class TestOrders:
    def test_get_orders_pagination(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU012", "initial_stock": 1000},
            headers=get_headers(),
        )

        # Create and confirm multiple reservations
        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU012",
                    "quantity": 10,
                    "idempotency_key": f"key_page_{i}",
                },
                headers=get_headers(),
            )
            res_id = res_response.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=get_headers())

        # Get first page
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
        assert data["total"] == 15

    def test_get_orders_default_pagination(self, client):
        # Create SKU
        client.post(
            "/skus",
            json={"sku": "SKU013", "initial_stock": 200},
            headers=get_headers(),
        )

        # Create orders
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU013",
                    "quantity": 10,
                    "idempotency_key": f"key_default_{i}",
                },
                headers=get_headers(),
            )
            res_id = res_response.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=get_headers())

        # Get orders with default parameters
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 5

    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 0
        assert data["total"] == 0


class TestHappyPath:
    def test_full_workflow(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "WORKFLOW_SKU", "initial_stock": 100},
            headers=get_headers(),
        )
        assert sku_response.status_code == 201
        sku_id = sku_response.json()["id"]

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={
                "sku": "WORKFLOW_SKU",
                "quantity": 50,
                "idempotency_key": "workflow_key",
            },
            headers=get_headers(),
        )
        assert res_response.status_code == 201
        res_id = res_response.json()["id"]
        assert res_response.json()["status"] == "PENDING"

        # Confirm reservation
        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=get_headers(),
        )
        assert confirm_response.status_code == 200

        # Get orders
        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        orders = orders_response.json()["orders"]
        assert len(orders) == 1
        assert orders[0]["sku"] == "WORKFLOW_SKU"
        assert orders[0]["quantity"] == 50
