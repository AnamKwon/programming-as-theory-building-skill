"""Tests for the API endpoints."""

import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, repository, service
from commerce_service.security import VALID_API_KEY


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the database before each test."""
    # Reinitialize with fresh in-memory database
    global repository, service
    from commerce_service.repository import Repository
    from commerce_service.service import CommerceService

    repository = Repository("sqlite:///:memory:")
    service = CommerceService(repository)

    # Patch the app's service
    app.repository = repository
    app.service = service

    yield


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "sku-001"
        assert data["name"] == "Widget"

    def test_create_sku_without_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget"},
        )
        assert response.status_code == 403
        assert "API key" in response.json()["detail"]

    def test_create_sku_with_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_create_duplicate_sku(self, client):
        client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Another"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestStockEndpoints:
    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        response = client.post(
            "/stock/sku-001/adjust",
            json={"delta": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 100

    def test_adjust_stock_without_api_key(self, client):
        response = client.post(
            "/stock/sku-001/adjust",
            json={"delta": 100},
        )
        assert response.status_code == 403

    def test_adjust_nonexistent_sku(self, client):
        response = client.post(
            "/stock/sku-001/adjust",
            json={"delta": 100},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]


class TestReservationEndpoints:
    def setup_method(self, method):
        """Setup SKU and stock for each test."""
        app.service.create_sku("sku-001", "Widget")
        app.service.adjust_stock("sku-001", 100)

    def test_create_reservation(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku_id": "sku-001",
                "quantity": 10,
                "idempotency_key": "key-001",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "sku-001"
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku_id": "sku-001",
                "quantity": 150,
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_reservation_idempotency(self, client):
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "sku-001",
                "quantity": 10,
                "idempotency_key": "key-001",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "sku-001",
                "quantity": 10,
                "idempotency_key": "key-001",
            },
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_cancel_reservation(self, client):
        res = client.post(
            "/reservations",
            json={"sku_id": "sku-001", "quantity": 10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrderEndpoints:
    def setup_method(self, method):
        """Setup SKU and stock for each test."""
        app.service.create_sku("sku-001", "Widget")
        app.service.adjust_stock("sku-001", 100)

    def test_confirm_reservation(self, client):
        res = client.post(
            "/reservations",
            json={"sku_id": "sku-001", "quantity": 10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == reservation_id
        assert data["quantity"] == 10
        assert data["status"] == "reserved"

    def test_confirm_reduces_stock(self, client):
        res = client.post(
            "/reservations",
            json={"sku_id": "sku-001", "quantity": 10},
            headers={"X-API-Key": VALID_API_KEY},
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

        # Try to reserve the remaining 90
        res2 = client.post(
            "/reservations",
            json={"sku_id": "sku-001", "quantity": 90},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert res2.status_code == 201

        # Try to reserve 91 (should fail)
        res3 = client.post(
            "/reservations",
            json={"sku_id": "sku-001", "quantity": 91},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert res3.status_code == 400

    def test_list_orders(self, client):
        # Create and confirm multiple orders
        for i in range(5):
            res = client.post(
                "/reservations",
                json={"sku_id": "sku-001", "quantity": 10},
                headers={"X-API-Key": VALID_API_KEY},
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": VALID_API_KEY},
            )

        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 1

    def test_list_orders_pagination(self, client):
        # Create 25 orders
        for i in range(25):
            res = client.post(
                "/reservations",
                json={"sku_id": "sku-001", "quantity": 2},
                headers={"X-API-Key": VALID_API_KEY},
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": VALID_API_KEY},
            )

        response1 = client.get("/orders?page=1&page_size=10")
        response2 = client.get("/orders?page=2&page_size=10")
        response3 = client.get("/orders?page=3&page_size=10")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        data1 = response1.json()
        data2 = response2.json()
        data3 = response3.json()

        assert len(data1["items"]) == 10
        assert len(data2["items"]) == 10
        assert len(data3["items"]) == 5
        assert data1["total"] == 25
        assert data1["total_pages"] == 3

    def test_list_orders_no_api_key_needed(self, client):
        response = client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
