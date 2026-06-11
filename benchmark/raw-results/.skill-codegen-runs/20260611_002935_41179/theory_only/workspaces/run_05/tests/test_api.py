import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def client(temp_db):
    """Create a test client with a temporary database"""
    # Override the app's repository and service
    from commerce_service import app as app_module
    app_module.repo = Repository(temp_db)
    app_module.service = CommerceService(app_module.repo)
    return TestClient(app)


@pytest.fixture
def api_key():
    """Return a valid API key"""
    return "test-api-key"


class TestHealth:
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        """Test creating a SKU with valid API key"""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        """Test that creating SKU without API key fails"""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100}
        )
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_create_sku_invalid_api_key(self, client):
        """Test that creating SKU with invalid API key fails"""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]


class TestStockAdjustment:
    def test_adjust_stock_success(self, client, api_key):
        """Test adjusting stock"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["available_stock"] == 150

    def test_adjust_stock_decrease(self, client, api_key):
        """Test decreasing stock"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 70

    def test_adjust_nonexistent_sku(self, client, api_key):
        """Test adjusting stock for non-existent SKU"""
        response = client.post(
            "/stock/adjust",
            json={"sku": "NONEXISTENT", "amount": 10},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 404

    def test_adjust_missing_api_key(self, client):
        """Test that adjusting stock without API key fails"""
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 10}
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, api_key):
        """Test creating a reservation"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"
        assert "id" in data

    def test_create_reservation_insufficient_stock(self, client, api_key):
        """Test reservation with insufficient stock"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 20},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client, api_key):
        """Test reservation idempotency"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response1 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        response2 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        data1 = response1.json()
        data2 = response2.json()
        assert data1["id"] == data2["id"]
        assert data2["quantity"] == 30  # Original quantity

    def test_create_reservation_idempotency_no_double_deduction(self, client, api_key):
        """Test that idempotent retry doesn't deduct stock twice"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        # Check stock is only deducted once
        response = client.get("/orders")
        # Get SKU to check stock
        from commerce_service.app import service
        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 70

    def test_create_reservation_missing_api_key(self, client):
        """Test that creating reservation without API key fails"""
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"}
        )
        assert response.status_code == 401


class TestConfirmationEndpoints:
    def test_confirm_reservation_success(self, client, api_key):
        """Test confirming a reservation"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CONFIRMED"

    def test_confirm_creates_order(self, client, api_key):
        """Test that confirming creates an order"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key}
        )
        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        orders = orders_response.json()
        assert len(orders["items"]) == 1
        assert orders["items"][0]["reservation_id"] == res_id

    def test_confirm_expired_reservation(self, client, api_key):
        """Test that confirming expired reservation fails"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]

        # Set created_at to be expired
        from commerce_service.app import service
        import sqlite3
        conn = sqlite3.connect(service.repo.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = datetime('now', '-301 seconds') WHERE id = ?",
            (res_id,)
        )
        conn.commit()
        conn.close()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400
        assert "Reservation expired" in response.json()["detail"]

    def test_confirm_expired_restores_stock(self, client, api_key):
        """Test that confirming expired reservation restores stock"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]

        from commerce_service.app import service
        import sqlite3
        conn = sqlite3.connect(service.repo.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = datetime('now', '-301 seconds') WHERE id = ?",
            (res_id,)
        )
        conn.commit()
        conn.close()

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key}
        )

        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 100

    def test_confirm_missing_api_key(self, client):
        """Test that confirming without API key fails"""
        response = client.post("/reservations/1/confirm")
        assert response.status_code == 401

    def test_confirm_nonexistent_reservation(self, client, api_key):
        """Test confirming non-existent reservation"""
        response = client.post(
            "/reservations/9999/confirm",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 404


class TestCancellationEndpoints:
    def test_cancel_reservation_success(self, client, api_key):
        """Test cancelling a reservation"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, client, api_key):
        """Test that cancellation restores stock"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key123"},
            headers={"X-API-Key": api_key}
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key}
        )

        from commerce_service.app import service
        sku = service.get_sku("SKU001")
        assert sku["available_stock"] == 100

    def test_cancel_missing_api_key(self, client):
        """Test that cancelling without API key fails"""
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 401

    def test_cancel_nonexistent_reservation(self, client, api_key):
        """Test cancelling non-existent reservation"""
        response = client.post(
            "/reservations/9999/cancel",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_get_orders_empty(self, client):
        """Test getting orders when none exist"""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 0

    def test_get_orders_pagination(self, client, api_key):
        """Test paginated order retrieval"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        # Create and confirm 15 orders
        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key{i}"},
                headers={"X-API-Key": api_key}
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key}
            )

        # Page 1 with default size
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 15

        # Page 2 with default size
        response = client.get("/orders?page=2")
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 2

    def test_get_orders_custom_page_size(self, client, api_key):
        """Test pagination with custom page size"""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        # Create and confirm 15 orders
        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key{i}"},
                headers={"X-API-Key": api_key}
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key}
            )

        response = client.get("/orders?page=1&size=5")
        data = response.json()
        assert len(data["items"]) == 5
        assert data["size"] == 5

    def test_get_orders_no_auth_required(self, client):
        """Test that GET /orders doesn't require authentication"""
        response = client.get("/orders")
        assert response.status_code == 200


class TestWorkflow:
    def test_happy_path_workflow(self, client, api_key):
        """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup"""
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "HAPPY001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        assert sku_response.status_code == 201

        # Create reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "HAPPY001", "quantity": 25, "idempotency_key": "happy-key"},
            headers={"X-API-Key": api_key}
        )
        assert res_response.status_code == 201
        res_data = res_response.json()
        assert res_data["status"] == "PENDING"

        # Confirm reservation
        confirm_response = client.post(
            f"/reservations/{res_data['id']}/confirm",
            headers={"X-API-Key": api_key}
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "CONFIRMED"

        # Get orders
        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        orders = orders_response.json()
        assert len(orders["items"]) == 1
        assert orders["items"][0]["reservation_id"] == res_data["id"]
