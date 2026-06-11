import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from src.commerce_service.app import app, repo, service
from src.commerce_service.security import VALID_API_TOKEN


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Clear database before each test."""
    repo.clear_db()
    yield


def get_auth_headers():
    """Helper to get authorization headers."""
    return {"Authorization": f"Bearer {VALID_API_TOKEN}"}


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSkuEndpoints:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST001"
        assert data["initial_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    def test_create_sku_no_auth(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100}
        )
        assert response.status_code == 401

    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST001", "amount": 50},
            headers=get_auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert data["new_stock"] == 150


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "PENDING"
        assert data["quantity"] == 50
        assert "id" in data
        assert "created_at" in data

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 30},
            headers=get_auth_headers()
        )

        response = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Insufficient stock"

    def test_idempotent_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        # First request
        response1 = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        assert response1.status_code == 201
        data1 = response1.json()
        reservation_id = data1["id"]

        # Second request with same key
        response2 = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        assert response2.status_code == 201
        data2 = response2.json()
        assert data2["id"] == reservation_id

    def test_reservation_unauthorized(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers={"Authorization": "Bearer invalid"}
        )
        assert response.status_code == 401


class TestConfirmationEndpoints:
    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"
        assert "order_id" in data

    def test_confirm_non_pending_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers()
        )

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers()
        )
        assert response.status_code == 400

    def test_expired_reservation_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        reservation_id = res.json()["id"]

        # Manually age the reservation
        reservation = repo.get_reservation(reservation_id)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
        conn = repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, reservation_id)
        )
        conn.commit()
        repo._close_conn(conn)

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers()
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Reservation expired"


class TestCancellationEndpoints:
    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=get_auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"
        assert data["stock_restored"] == 50

    def test_cancel_non_pending_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 100},
            headers=get_auth_headers()
        )

        res = client.post(
            "/reservations",
            json={
                "sku": "TEST001",
                "quantity": 50,
                "idempotency_key": "key123"
            },
            headers=get_auth_headers()
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers()
        )

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=get_auth_headers()
        )
        assert response.status_code == 400


class TestOrderEndpoints:
    def test_get_orders_paginated(self, client):
        client.post(
            "/skus",
            json={"sku": "TEST001", "initial_stock": 1000},
            headers=get_auth_headers()
        )

        # Create and confirm 15 reservations
        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku": "TEST001",
                    "quantity": 10,
                    "idempotency_key": f"key{i}"
                },
                headers=get_auth_headers()
            )
            reservation_id = res.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers=get_auth_headers()
            )

        # Get first page
        response = client.get(
            "/orders?page=1&size=10",
            headers=get_auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 15

        # Get second page
        response = client.get(
            "/orders?page=2&size=10",
            headers=get_auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 2
        assert data["total"] == 15

    def test_get_orders_unauthorized(self, client):
        response = client.get(
            "/orders",
            headers={"Authorization": "Bearer invalid"}
        )
        assert response.status_code == 401


class TestHappyPath:
    def test_full_workflow(self, client):
        # Create SKU
        sku_res = client.post(
            "/skus",
            json={"sku": "LAPTOP001", "initial_stock": 10},
            headers=get_auth_headers()
        )
        assert sku_res.status_code == 201

        # Create reservation
        res = client.post(
            "/reservations",
            json={
                "sku": "LAPTOP001",
                "quantity": 3,
                "idempotency_key": "order-123"
            },
            headers=get_auth_headers()
        )
        assert res.status_code == 201
        reservation_id = res.json()["id"]

        # Confirm reservation
        confirm_res = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers()
        )
        assert confirm_res.status_code == 200
        order_id = confirm_res.json()["order_id"]

        # Get orders
        orders_res = client.get(
            "/orders?page=1&size=10",
            headers=get_auth_headers()
        )
        assert orders_res.status_code == 200
        data = orders_res.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == order_id
