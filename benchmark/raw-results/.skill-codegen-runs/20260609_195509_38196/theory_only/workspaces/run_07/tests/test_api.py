"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.app import app, get_db
from commerce_service.models import Base

# In-memory database for tests
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(bind=engine)


def override_get_db():
    """Override database dependency for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

HEADERS = {"X-API-Key": "dev-key-12345"}


class TestHealthCheck:
    """Test health endpoint."""

    def test_health_check(self):
        """Health check returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    """Test SKU creation and stock adjustment."""

    def test_create_sku(self):
        """Creating a SKU returns initial stock."""
        response = client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["available"] == 100
        assert data["reserved"] == 0
        assert data["total"] == 100

    def test_create_sku_without_api_key(self):
        """Creating a SKU without API key fails."""
        response = client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100})
        assert response.status_code == 403

    def test_create_sku_invalid_api_key(self):
        """Creating a SKU with invalid API key fails."""
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "quantity": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock(self):
        """Adjusting stock updates available."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        response = client.post(
            "/skus/WIDGET-001/adjust-stock",
            json={"delta": 50, "reason": "restock"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available"] == 150


class TestReservationFlow:
    """Test reservation creation, confirmation, and cancellation."""

    def setup_method(self):
        """Reset database before each test."""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def test_create_reservation_success(self):
        """Creating a reservation reserves stock."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["quantity"] == 30

    def test_create_reservation_insufficient_stock(self):
        """Creating a reservation with insufficient stock fails."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 150, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert "Insufficient" in response.json()["detail"]

    def test_create_reservation_idempotent(self):
        """Retrying with same idempotency key returns same reservation."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        res1 = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res2 = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["id"] == res2.json()["id"]

    def test_confirm_reservation(self):
        """Confirming a reservation creates an order."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        reservation_id = res.json()["id"]
        response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    def test_confirm_non_pending_reservation(self):
        """Confirming a non-pending reservation fails."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        reservation_id = res.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
        assert response.status_code == 400
        assert "Cannot confirm" in response.json()["detail"]

    def test_cancel_reservation(self):
        """Cancelling a reservation frees stock."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        reservation_id = res.json()["id"]
        response = client.post(f"/reservations/{reservation_id}/cancel", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"


class TestOrderEndpoints:
    """Test order listing and retrieval."""

    def setup_method(self):
        """Reset database before each test."""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def test_list_orders_empty(self):
        """Listing orders when empty returns zero."""
        response = client.get("/orders", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["orders"] == []

    def test_list_orders_with_pagination(self):
        """Listing orders respects pagination."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 1000}, headers=HEADERS)
        for i in range(5):
            res = client.post(
                "/reservations",
                json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": f"key-{i}"},
                headers=HEADERS,
            )
            res_id = res.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        response = client.get("/orders?page=1&page_size=2", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["orders"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_orders_invalid_page(self):
        """Listing with invalid page parameter fails."""
        response = client.get("/orders?page=0", headers=HEADERS)
        assert response.status_code == 400

    def test_get_order_success(self):
        """Getting a specific order returns order details."""
        client.post("/skus", json={"sku": "WIDGET-001", "quantity": 100}, headers=HEADERS)
        res = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res.json()["id"]
        confirm_res = client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        # Order ID is in a Location header or returned separately; for now, we get it from list
        list_res = client.get("/orders", headers=HEADERS)
        order_id = list_res.json()["orders"][0]["id"]
        response = client.get(f"/orders/{order_id}", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["status"] == "confirmed"

    def test_get_order_not_found(self):
        """Getting a non-existent order returns 404."""
        response = client.get("/orders/9999", headers=HEADERS)
        assert response.status_code == 404

    def test_mutation_without_api_key(self):
        """Mutation endpoints require API key."""
        response = client.get("/orders")
        assert response.status_code == 403
