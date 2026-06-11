"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, get_repository, get_service
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import VALID_API_TOKEN


@pytest.fixture
def repository():
    """Create an in-memory repository for testing."""
    return Repository(db_path=":memory:")


@pytest.fixture
def service(repository):
    """Create a service instance."""
    return CommerceService(repository)


@pytest.fixture
def client(repository, service):
    """Create a test client with dependencies."""
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHealth:
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_token(self, client):
        """Test creating SKU without authentication."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
        )
        assert response.status_code == 401
        assert "Missing API token" in response.json()["detail"]

    def test_create_sku_invalid_token(self, client):
        """Test creating SKU with invalid token."""
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": "invalid-token"},
        )
        assert response.status_code == 401
        assert "Invalid API token" in response.json()["detail"]

    def test_adjust_stock_success(self, client):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 50},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["new_stock"] == 150

    def test_adjust_stock_missing_token(self, client):
        """Test adjusting stock without authentication."""
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 50},
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["quantity"] == 50
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        """Test reservation with insufficient stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 30},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self, client):
        """Test idempotent reservation creation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        first = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        first_data = first.json()

        second = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        second_data = second.json()

        assert first_data["id"] == second_data["id"]
        assert first_data["quantity"] == second_data["quantity"]

    def test_create_reservation_missing_token(self, client):
        """Test creating reservation without authentication."""
        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
        )
        assert response.status_code == 401


class TestConfirmationEndpoints:
    def test_confirm_reservation_success(self, client):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"
        assert data["order_id"] == 1

    def test_confirm_reservation_missing_token(self, client):
        """Test confirming without authentication."""
        response = client.post("/reservations/1/confirm")
        assert response.status_code == 401

    def test_confirm_reservation_not_pending(self, client):
        """Test confirming a non-PENDING reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 400

    def test_confirm_reservation_expired(self, client, monkeypatch):
        """Test confirming an expired reservation."""
        from datetime import datetime, timedelta
        from commerce_service.service import RESERVATION_EXPIRATION_SECONDS

        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        reservation_id = res.json()["id"]

        def mock_utcnow():
            now = datetime.utcnow()
            return now + timedelta(seconds=RESERVATION_EXPIRATION_SECONDS + 1)

        monkeypatch.setattr(__import__('commerce_service.service', fromlist=['datetime']).datetime, 'utcnow', mock_utcnow)

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()


class TestCancellationEndpoints:
    def test_cancel_reservation_success(self, client):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_reservation_missing_token(self, client):
        """Test cancelling without authentication."""
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 401

    def test_cancel_reservation_restores_stock(self, client):
        """Test that cancellation restores stock."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Token": VALID_API_TOKEN},
        )


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        """Test listing orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orders_pagination(self, client):
        """Test order pagination."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 1000},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        for i in range(25):
            res = client.post(
                "/reservations",
                json={"sku": "SKU-001", "quantity": 1, "idempotency_key": f"idem-{i}"},
                headers={"X-API-Token": VALID_API_TOKEN},
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Token": VALID_API_TOKEN},
            )

        page1 = client.get("/orders?page=1&size=10")
        assert page1.status_code == 200
        data1 = page1.json()
        assert len(data1["items"]) == 10
        assert data1["total"] == 25
        assert data1["page"] == 1

        page2 = client.get("/orders?page=2&size=10")
        data2 = page2.json()
        assert len(data2["items"]) == 10

        page3 = client.get("/orders?page=3&size=10")
        data3 = page3.json()
        assert len(data3["items"]) == 5

    def test_list_orders_default_pagination(self, client):
        """Test orders pagination with default parameters."""
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Token": VALID_API_TOKEN},
        )

        for i in range(5):
            res = client.post(
                "/reservations",
                json={"sku": "SKU-001", "quantity": 1, "idempotency_key": f"idem-{i}"},
                headers={"X-API-Token": VALID_API_TOKEN},
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Token": VALID_API_TOKEN},
            )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 1
        assert data["size"] == 10


class TestWorkflow:
    def test_happy_path_workflow(self, client):
        """Test the complete happy path: SKU -> Reserve -> Confirm -> Order lookup."""
        sku_res = client.post(
            "/skus",
            json={"sku": "SKU-TEST", "initial_stock": 200},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert sku_res.status_code == 201

        res_res = client.post(
            "/reservations",
            json={"sku": "SKU-TEST", "quantity": 75, "idempotency_key": "happy-path"},
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert res_res.status_code == 201
        reservation = res_res.json()
        assert reservation["status"] == "PENDING"

        conf_res = client.post(
            f"/reservations/{reservation['id']}/confirm",
            headers={"X-API-Token": VALID_API_TOKEN},
        )
        assert conf_res.status_code == 200
        confirmed = conf_res.json()
        assert confirmed["status"] == "CONFIRMED"
        order_id = confirmed["order_id"]

        orders_res = client.get("/orders")
        assert orders_res.status_code == 200
        orders = orders_res.json()
        assert len(orders["items"]) == 1
        assert orders["items"][0]["id"] == order_id
        assert orders["items"][0]["reservation_id"] == reservation["id"]
