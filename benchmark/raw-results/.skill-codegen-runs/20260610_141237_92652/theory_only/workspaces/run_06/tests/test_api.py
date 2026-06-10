import pytest
import tempfile
import os
from fastapi.testclient import TestClient

from commerce_service.app import app
from commerce_service.repository import Repository


@pytest.fixture(autouse=True)
def setup_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    from commerce_service import app as app_module
    app_module.repo = Repository(path)
    app_module.service = app_module.Service(app_module.repo)

    yield

    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_headers():
    return {"X-API-Key": "test-key-123"}


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, valid_headers):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU001"
        assert response.json()["stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150

    def test_adjust_stock_negative(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 70


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 20},
            headers=valid_headers,
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 50, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
        )
        assert response.status_code == 401

    def test_idempotency_returns_same_response(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        response1 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        )
        response2 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        )

        assert response1.json() == response2.json()

    def test_confirm_reservation_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        ).json()

        response = client.post(
            f"/reservations/{res['id']}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"
        assert "order_id" in data

    def test_confirm_expired_reservation(self, client, valid_headers):
        from commerce_service import app as app_module
        from datetime import datetime, timedelta

        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        res_id = app_module.repo.create_reservation("SKU001", 30, "idempotency-1")
        app_module.repo.adjust_stock("SKU001", -30)

        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        import sqlite3
        conn = app_module.repo.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (old_time, res_id))
        conn.commit()
        conn.close()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_confirm_non_pending_reservation(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        ).json()

        client.post(
            f"/reservations/{res['id']}/confirm",
            headers=valid_headers,
        )

        response = client.post(
            f"/reservations/{res['id']}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 400

    def test_cancel_reservation_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        ).json()

        response = client.post(
            f"/reservations/{res['id']}/cancel",
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_non_pending_reservation(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        ).json()

        client.post(
            f"/reservations/{res['id']}/confirm",
            headers=valid_headers,
        )

        response = client.post(
            f"/reservations/{res['id']}/cancel",
            headers=valid_headers,
        )
        assert response.status_code == 400


class TestOrderEndpoints:
    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 0

    def test_get_orders_with_data(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        ).json()

        client.post(
            f"/reservations/{res['id']}/confirm",
            headers=valid_headers,
        )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 1
        assert data["orders"][0]["sku"] == "SKU001"
        assert data["total"] == 1

    def test_get_orders_pagination(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers=valid_headers,
        )

        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"idempotency-{i}"},
                headers=valid_headers,
            ).json()

            client.post(
                f"/reservations/{res['id']}/confirm",
                headers=valid_headers,
            )

        page1 = client.get("/orders?page=1&size=10")
        assert page1.status_code == 200
        data1 = page1.json()
        assert len(data1["orders"]) == 10
        assert data1["page"] == 1
        assert data1["total"] == 15

        page2 = client.get("/orders?page=2&size=10")
        assert page2.status_code == 200
        data2 = page2.json()
        assert len(data2["orders"]) == 5
        assert data2["page"] == 2


class TestHappyPath:
    def test_complete_workflow(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=valid_headers,
        )

        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "idempotency-1"},
            headers=valid_headers,
        ).json()
        assert res["status"] == "PENDING"

        confirmed = client.post(
            f"/reservations/{res['id']}/confirm",
            headers=valid_headers,
        ).json()
        assert confirmed["status"] == "CONFIRMED"
        assert "order_id" in confirmed

        orders = client.get("/orders").json()
        assert len(orders["orders"]) == 1
        assert orders["orders"][0]["id"] == confirmed["order_id"]
        assert orders["orders"][0]["sku"] == "SKU001"
        assert orders["orders"][0]["quantity"] == 30
