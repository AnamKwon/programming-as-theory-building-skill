import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from unittest.mock import patch

from commerce_service.app import app, repo, service
from commerce_service.repository import Repository
from commerce_service.security import VALID_API_KEY


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    os.unlink(path)


@pytest.fixture
def test_client(temp_db):
    """Create a test client with a fresh database."""
    test_repo = Repository(temp_db)
    from commerce_service.service import CommerceService

    test_service = CommerceService(test_repo)

    with patch("commerce_service.app.repo", test_repo):
        with patch("commerce_service.app.service", test_service):
            client = TestClient(app)
            yield client


def headers(api_key=VALID_API_KEY):
    """Return headers with API key."""
    return {"X-API-Key": api_key}


class TestHealthCheck:
    def test_health_check(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku(self, test_client):
        response = test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers=headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "SKU001"
        assert data["available_stock"] == 100
        assert data["reserved_stock"] == 0

    def test_create_sku_missing_api_key(self, test_client):
        response = test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_api_key(self, test_client):
        response = test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers=headers(),
        )
        response = test_client.post(
            "/skus/SKU001/stock",
            json={"delta": 50},
            headers=headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 150


class TestReservationEndpoints:
    def test_create_reservation_success(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers=headers(),
        )
        response = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 10
        assert data["status"] == "active"
        assert "expires_at" in data

    def test_create_reservation_idempotent(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers=headers(),
        )
        res1 = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=headers(),
        )
        res2 = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=headers(),
        )
        assert res1.status_code == 201
        assert res2.status_code == 200
        assert res1.json()["id"] == res2.json()["id"]

    def test_create_reservation_insufficient_stock(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 50},
            headers=headers(),
        )
        response = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 100,
                "idempotency_key": "key-1",
            },
            headers=headers(),
        )
        assert response.status_code == 409

    def test_confirm_reservation(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers=headers(),
        )
        res = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=headers(),
        )
        res_id = res.json()["id"]

        response = test_client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers=headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert "order_id" in data

    def test_confirm_nonexistent_reservation(self, test_client):
        response = test_client.post(
            "/reservations/nonexistent/confirm",
            json={},
            headers=headers(),
        )
        assert response.status_code == 404

    def test_cancel_reservation(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
            headers=headers(),
        )
        res = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers=headers(),
        )
        res_id = res.json()["id"]

        response = test_client.post(
            f"/reservations/{res_id}/cancel",
            json={},
            headers=headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_cancel_reservation_requires_auth(self, test_client):
        response = test_client.post(
            "/reservations/any-id/cancel",
            json={},
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    def test_list_orders_empty(self, test_client):
        response = test_client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_list_orders_pagination(self, test_client):
        test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 1000},
            headers=headers(),
        )

        for i in range(25):
            res = test_client.post(
                "/reservations",
                json={
                    "sku_id": "SKU001",
                    "quantity": 1,
                    "idempotency_key": f"key-{i}",
                },
                headers=headers(),
            )
            res_id = res.json()["id"]
            test_client.post(
                f"/reservations/{res_id}/confirm",
                json={},
                headers=headers(),
            )

        response = test_client.get("/orders?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 25
        assert data["page"] == 1

        response = test_client.get("/orders?page=2&page_size=10")
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["page"] == 2

        response = test_client.get("/orders?page=3&page_size=10")
        data = response.json()
        assert len(data["orders"]) == 5
        assert data["page"] == 3

    def test_list_orders_custom_page_size(self, test_client):
        response = test_client.get("/orders?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 5

    def test_list_orders_invalid_page(self, test_client):
        response = test_client.get("/orders?page=0")
        assert response.status_code == 422

    def test_list_orders_page_size_too_large(self, test_client):
        response = test_client.get("/orders?page_size=101")
        assert response.status_code == 422


class TestAuthorizationFlow:
    def test_create_sku_requires_auth(self, test_client):
        response = test_client.post(
            "/skus",
            json={"id": "SKU001", "available_stock": 100},
        )
        assert response.status_code == 403

    def test_adjust_stock_requires_auth(self, test_client):
        response = test_client.post(
            "/skus/SKU001/stock",
            json={"delta": 10},
        )
        assert response.status_code == 403

    def test_create_reservation_requires_auth(self, test_client):
        response = test_client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": "key-1",
            },
        )
        assert response.status_code == 403

    def test_confirm_reservation_requires_auth(self, test_client):
        response = test_client.post(
            "/reservations/any-id/confirm",
            json={},
        )
        assert response.status_code == 403

    def test_order_list_does_not_require_auth(self, test_client):
        response = test_client.get("/orders")
        assert response.status_code == 200
