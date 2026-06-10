"""Tests for the FastAPI endpoints."""

import pytest
import tempfile
from decimal import Decimal
from pathlib import Path
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository
import src.commerce_service.app as app_module


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


@pytest.fixture
def client(temp_db):
    """Create a test client with a temporary database."""
    repo = Repository(db_path=temp_db)
    app_module._repo = repo

    from src.commerce_service.service import CommerceService
    app_module._service = CommerceService(repo)

    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "WIDGET-001"
        assert data["name"] == "Widget"
        assert data["stock_quantity"] == 0

    def test_create_sku_missing_auth(self, client):
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
        )
        assert response.status_code == 401

    def test_create_sku_invalid_auth(self, client):
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_create_duplicate_sku(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        response = client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 409

    def test_get_sku(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        response = client.get("/skus/WIDGET-001")
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "WIDGET-001"

    def test_get_nonexistent_sku(self, client):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404


class TestStockEndpoints:
    def test_adjust_stock_increase(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["new_quantity"] == 100

    def test_adjust_stock_missing_auth(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
        )
        assert response.status_code == 401

    def test_adjust_stock_negative_fails(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": -100},
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
            headers={"X-API-Key": "secret-key"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "WIDGET-001"
        assert data["quantity"] == 50
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 20},
            headers={"X-API-Key": "secret-key"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 409

    def test_idempotent_reservation_creation(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
            headers={"X-API-Key": "secret-key"},
        )

        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )

        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
            headers={"X-API-Key": "secret-key"},
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )
        reservation_id = res_response.json()["reservation_id"]

        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": "secret-key"},
        )
        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert data["status"] == "confirmed"

    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
            headers={"X-API-Key": "secret-key"},
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )
        reservation_id = res_response.json()["reservation_id"]

        cancel_response = client.post(
            f"/reservations/{reservation_id}/cancel",
            json={},
            headers={"X-API-Key": "secret-key"},
        )
        assert cancel_response.status_code == 200
        data = cancel_response.json()
        assert data["status"] == "cancelled"

    def test_reservation_requires_auth(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
        )
        assert response.status_code == 401


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        response = client.get(
            "/orders",
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0
        assert data["has_more"] is False

    def test_list_orders_with_pagination(self, client):
        # Setup: create SKU, stock, and multiple confirmed reservations
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 1000},
            headers={"X-API-Key": "secret-key"},
        )

        # Create 25 orders
        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={
                    "sku_id": "WIDGET-001",
                    "quantity": 10,
                    "idempotency_key": f"order-{i}",
                },
                headers={"X-API-Key": "secret-key"},
            )
            reservation_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={},
                headers={"X-API-Key": "secret-key"},
            )

        # Page 1
        response1 = client.get(
            "/orders?page=1&page_size=20",
            headers={"X-API-Key": "secret-key"},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) == 20
        assert data1["total"] == 25
        assert data1["has_more"] is True

        # Page 2
        response2 = client.get(
            "/orders?page=2&page_size=20",
            headers={"X-API-Key": "secret-key"},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 5
        assert data2["has_more"] is False

    def test_get_order(self, client):
        client.post(
            "/skus",
            json={
                "sku_id": "WIDGET-001",
                "name": "Widget",
                "unit_price": "19.99",
            },
            headers={"X-API-Key": "secret-key"},
        )
        client.post(
            "/stock/adjust",
            json={"sku_id": "WIDGET-001", "quantity_delta": 100},
            headers={"X-API-Key": "secret-key"},
        )

        res_response = client.post(
            "/reservations",
            json={
                "sku_id": "WIDGET-001",
                "quantity": 50,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": "secret-key"},
        )
        reservation_id = res_response.json()["reservation_id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": "secret-key"},
        )

        # Get the order
        orders_response = client.get(
            "/orders",
            headers={"X-API-Key": "secret-key"},
        )
        order_id = orders_response.json()["items"][0]["order_id"]

        response = client.get(
            f"/orders/{order_id}",
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["sku_id"] == "WIDGET-001"

    def test_list_orders_requires_auth(self, client):
        response = client.get("/orders")
        assert response.status_code == 401

    def test_get_nonexistent_order(self, client):
        response = client.get(
            "/orders/nonexistent",
            headers={"X-API-Key": "secret-key"},
        )
        assert response.status_code == 404
