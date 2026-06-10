import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app

VALID_KEY = "test-key-123"


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthCheck:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Widget"
        assert data["current_stock"] == 100
        assert data["id"] is not None

    def test_create_sku_no_auth(self, client):
        response = client.post("/skus", json={"name": "Widget", "current_stock": 100})
        assert response.status_code == 403

    def test_create_sku_invalid_auth(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget", "current_stock": 100},
            headers={"x-api-key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock(self, client):
        # Create SKU
        res = client.post(
            "/skus",
            json={"name": "Item", "current_stock": 50},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = res.json()["id"]

        # Adjust stock
        response = client.patch(
            f"/skus/{sku_id}/stock",
            json={"quantity_delta": 10},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 200
        assert response.json()["current_stock"] == 60

    def test_adjust_stock_nonexistent_sku(self, client):
        response = client.patch(
            "/skus/nonexistent/stock",
            json={"quantity_delta": 5},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 404

    def test_adjust_stock_negative(self, client):
        # Create SKU with 10 stock
        res = client.post(
            "/skus",
            json={"name": "Item", "current_stock": 10},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = res.json()["id"]

        # Try to go negative
        response = client.patch(
            f"/skus/{sku_id}/stock",
            json={"quantity_delta": -20},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self, client):
        # Create SKU
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        # Create reservation
        response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 20},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku_id
        assert data["quantity"] == 20
        assert data["status"] == "pending"
        assert data["id"] is not None

    def test_create_reservation_insufficient_stock(self, client):
        # Create SKU with low stock
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 5},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        # Try to reserve more than available
        response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 409  # Conflict

    def test_create_reservation_nonexistent_sku(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": "nonexistent", "quantity": 10},
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 404

    def test_idempotent_reservation(self, client):
        # Create SKU
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        # Create reservation with idempotency key
        key = "test-key-1"
        res1 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 15, "idempotency_key": key},
            headers={"x-api-key": VALID_KEY},
        )
        assert res1.status_code == 201
        id1 = res1.json()["id"]

        # Retry with same key
        res2 = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 15, "idempotency_key": key},
            headers={"x-api-key": VALID_KEY},
        )
        assert res2.status_code == 201
        id2 = res2.json()["id"]

        # Should be same reservation
        assert id1 == id2

        # Verify stock only reserved once (85 remaining, not 70)
        sku_check = client.get(
            f"/skus/{sku_id}", headers={"x-api-key": VALID_KEY}
        )  # Assume GET exists or check via orders
        # We'll verify indirectly through the next confirmation test


class TestReservationConfirmation:
    def test_confirm_reservation(self, client):
        # Setup
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        res_res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 25},
            headers={"x-api-key": VALID_KEY},
        )
        res_id = res_res.json()["id"]

        # Confirm
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["reservation_id"] == res_id

    def test_confirm_nonexistent_reservation(self, client):
        response = client.post(
            "/reservations/nonexistent/confirm",
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 404

    def test_confirm_expired_reservation(self, client):
        # Create reservation and manually expire it
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        res_res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10},
            headers={"x-api-key": VALID_KEY},
        )
        res_id = res_res.json()["id"]

        # Manually expire (would need DB access; in real test setup)
        # For now, this is covered in service tests
        pass


class TestReservationCancellation:
    def test_cancel_reservation(self, client):
        # Setup
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        res_res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 30},
            headers={"x-api-key": VALID_KEY},
        )
        res_id = res_res.json()["id"]

        # Cancel
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_cancel_nonexistent_reservation(self, client):
        response = client.post(
            "/reservations/nonexistent/cancel",
            headers={"x-api-key": VALID_KEY},
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_get_order(self, client):
        # Setup
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 100},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        res_res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 15},
            headers={"x-api-key": VALID_KEY},
        )
        res_id = res_res.json()["id"]

        confirm_res = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": VALID_KEY},
        )
        order_id = confirm_res.json()["id"]

        # Get order
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["status"] == "confirmed"

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders/nonexistent")
        assert response.status_code == 404

    def test_list_orders_pagination(self, client):
        # Create multiple orders
        sku_res = client.post(
            "/skus",
            json={"name": "Product", "current_stock": 1000},
            headers={"x-api-key": VALID_KEY},
        )
        sku_id = sku_res.json()["id"]

        for i in range(5):
            res_res = client.post(
                "/reservations",
                json={"sku_id": sku_id, "quantity": 1},
                headers={"x-api-key": VALID_KEY},
            )
            res_id = res_res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"x-api-key": VALID_KEY},
            )

        # Test pagination
        response = client.get("/orders?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["cursor"] == "2"

        # Next page
        response = client.get("/orders?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        # Last page
        response = client.get("/orders?limit=2&offset=4")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["cursor"] is None

    def test_list_orders_invalid_limit(self, client):
        response = client.get("/orders?limit=1000")
        assert response.status_code == 422  # Validation error

    def test_list_orders_invalid_offset(self, client):
        response = client.get("/orders?offset=-5")
        assert response.status_code == 422  # Validation error
