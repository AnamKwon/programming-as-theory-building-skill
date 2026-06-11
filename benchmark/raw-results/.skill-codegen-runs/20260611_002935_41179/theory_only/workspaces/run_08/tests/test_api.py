"""Tests for the API endpoints."""

import pytest
from datetime import datetime, timedelta


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint returns 200 with ok status."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_check_no_auth_required(self, client):
        """Test health check does not require authentication."""
        response = client.get("/health")

        assert response.status_code == 200


class TestSKUEndpoints:
    """Tests for SKU management endpoints."""

    def test_create_sku_success(self, client, auth_headers):
        """Test creating a new SKU returns 201."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["available_stock"] == 100
        assert data["id"] is not None

    def test_create_sku_no_auth(self, client):
        """Test creating SKU without auth token returns 401."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )

        assert response.status_code == 401

    def test_create_sku_invalid_auth(self, client):
        """Test creating SKU with invalid token returns 401."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Token": "invalid-token"},
        )

        assert response.status_code == 401

    def test_adjust_stock_success(self, client, auth_headers):
        """Test adjusting stock returns 200 with updated stock."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["adjusted_by"] == 50
        assert data["new_stock"] == 150

    def test_adjust_stock_negative(self, client, auth_headers):
        """Test adjusting stock with negative amount."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers=auth_headers,
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["new_stock"] == 70

    def test_adjust_stock_no_auth(self, client):
        """Test adjusting stock without auth returns 401."""
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 10},
        )

        assert response.status_code == 401


class TestReservationEndpoints:
    """Tests for reservation endpoints."""

    @pytest.fixture(autouse=True)
    def setup_sku(self, client, auth_headers):
        """Create a SKU for reservation tests."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers=auth_headers,
        )

    def test_create_reservation_success(self, client, auth_headers):
        """Test creating a reservation returns 201."""
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 25
        assert data["status"] == "PENDING"
        assert data["idempotency_key"] == "idem-key-1"
        assert data["id"] is not None

    def test_create_reservation_insufficient_stock(self, client, auth_headers):
        """Test reservation with insufficient stock returns 400."""
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 2000,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_create_reservation_idempotency(self, client, auth_headers):
        """Test idempotent retry returns same reservation without double-deduction."""
        first_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )

        second_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )

        first_data = first_response.json()
        second_data = second_response.json()

        assert first_response.status_code == 201
        assert second_response.status_code == 201
        assert first_data["id"] == second_data["id"]

    def test_create_reservation_no_auth(self, client):
        """Test creating reservation without auth returns 401."""
        response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
        )

        assert response.status_code == 401

    def test_confirm_reservation_success(self, client, auth_headers):
        """Test confirming a reservation returns 200 with order."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == res_id
        assert data["order_id"] is not None
        assert data["status"] == "CONFIRMED"

    def test_confirm_reservation_non_pending(self, client, auth_headers):
        """Test confirming a non-pending reservation returns 400."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_confirm_reservation_expired(self, client, auth_headers, service):
        """Test confirming an expired reservation (>300 seconds) returns 400."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        # Manually expire the reservation
        conn = service.db.get_connection()
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        cursor.execute(
            "UPDATE reservations SET created_at = ? WHERE id = ?",
            (old_time, res_id),
        )
        conn.commit()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Reservation expired"

    def test_confirm_reservation_no_auth(self, client, auth_headers):
        """Test confirming reservation without auth returns 401."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        response = client.post(f"/reservations/{res_id}/confirm")

        assert response.status_code == 401

    def test_cancel_reservation_success(self, client, auth_headers):
        """Test cancelling a reservation returns 200."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == res_id
        assert data["status"] == "CANCELLED"
        assert data["restored_stock"] == 25

    def test_cancel_reservation_non_pending(self, client, auth_headers):
        """Test cancelling a non-pending reservation returns 400."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_cancel_reservation_no_auth(self, client, auth_headers):
        """Test cancelling reservation without auth returns 401."""
        create_response = client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=auth_headers,
        )
        res_id = create_response.json()["id"]

        response = client.post(f"/reservations/{res_id}/cancel")

        assert response.status_code == 401


class TestOrderEndpoints:
    """Tests for order endpoints."""

    @pytest.fixture(autouse=True)
    def setup_orders(self, client, auth_headers):
        """Create SKUs and orders for testing."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 10000},
            headers=auth_headers,
        )

        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "SKU001",
                    "quantity": 10,
                    "idempotency_key": f"idem-key-{i}",
                },
                headers=auth_headers,
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers=auth_headers,
            )

    def test_get_orders_default_pagination(self, client):
        """Test getting orders with default pagination."""
        response = client.get("/orders")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["pages"] == 3

    def test_get_orders_custom_page_size(self, client):
        """Test getting orders with custom page size."""
        response = client.get("/orders?page=1&size=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["size"] == 5
        assert data["pages"] == 5

    def test_get_orders_page_2(self, client):
        """Test pagination offset behavior on page 2."""
        page1 = client.get("/orders?page=1&size=10").json()
        page2 = client.get("/orders?page=2&size=10").json()

        assert len(page2["items"]) == 10
        assert page2["page"] == 2

        page1_ids = {order["id"] for order in page1["items"]}
        page2_ids = {order["id"] for order in page2["items"]}
        assert len(page1_ids & page2_ids) == 0

    def test_get_orders_page_3(self, client):
        """Test pagination on last partial page."""
        response = client.get("/orders?page=3&size=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 3

    def test_get_orders_no_auth_required(self, client):
        """Test getting orders does not require authentication."""
        response = client.get("/orders")

        assert response.status_code == 200


class TestHappyPath:
    """End-to-end happy path workflow test."""

    def test_sku_reserve_confirm_order_lookup(self, client, auth_headers):
        """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
        sku_response = client.post(
            "/skus",
            json={"sku": "HAPPY_SKU", "initial_stock": 1000},
            headers=auth_headers,
        )
        assert sku_response.status_code == 201

        res_response = client.post(
            "/reservations",
            json={
                "sku": "HAPPY_SKU",
                "quantity": 100,
                "idempotency_key": "happy-path-key",
            },
            headers=auth_headers,
        )
        assert res_response.status_code == 201
        res_id = res_response.json()["id"]

        confirm_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=auth_headers,
        )
        assert confirm_response.status_code == 200
        order_id = confirm_response.json()["order_id"]

        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        orders = orders_response.json()
        assert any(o["id"] == order_id for o in orders["items"])
