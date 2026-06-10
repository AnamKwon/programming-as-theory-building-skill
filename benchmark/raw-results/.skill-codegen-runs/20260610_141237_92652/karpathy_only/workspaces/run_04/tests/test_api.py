import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app, get_service
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def client():
    from src.commerce_service.app import app
    # Create a fresh service with a fresh database for this test
    test_repo = Repository(db_path=":memory:")
    test_service = CommerceService(test_repo)

    app.dependency_overrides[get_service] = lambda: test_service

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    return "test-key-123"


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        response = client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PROD001"
        assert data["initial_stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100}
        )
        assert response.status_code == 401

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401

    def test_create_duplicate_sku(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 50},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400


class TestStockAdjustment:
    def test_adjust_stock_increase(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "PROD001", "amount": 50},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert response.json()["updated_stock"] == 150

    def test_adjust_stock_decrease(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "PROD001", "amount": -30},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert response.json()["updated_stock"] == 70

    def test_adjust_stock_nonexistent(self, client, api_key):
        response = client.post(
            "/stock/adjust",
            json={"sku": "NONEXISTENT", "amount": 50},
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400

    def test_adjust_stock_missing_api_key(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku": "PROD001", "amount": 50}
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PROD001"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 50},
            headers={"X-API-Key": api_key}
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 100,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            }
        )
        assert response.status_code == 401


class TestConfirmReservation:
    def test_confirm_reservation_success(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CONFIRMED"
        assert data["order_id"] > 0

    def test_confirm_reservation_nonexistent(self, client, api_key):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400
        assert "Reservation not found" in response.json()["detail"]

    def test_confirm_reservation_expired(self, client, api_key, monkeypatch):
        # Set a fixed creation time
        creation_time = 1000.0
        monkeypatch.setattr("src.commerce_service.service.time.time", lambda: creation_time)

        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        reservation_id = res_response.json()["id"]

        # Now set time to after expiry
        expiry_time = creation_time + 400
        monkeypatch.setattr("src.commerce_service.service.time.time", lambda: expiry_time)

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400
        assert "Reservation expired" in response.json()["detail"]

    def test_confirm_reservation_missing_api_key(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        reservation_id = res_response.json()["id"]

        response = client.post(f"/reservations/{reservation_id}/confirm")
        assert response.status_code == 401


class TestCancelReservation:
    def test_cancel_reservation_success(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"
        assert data["stock_restored"] == 30

    def test_cancel_reservation_nonexistent(self, client, api_key):
        response = client.post(
            "/reservations/999/cancel",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 400
        assert "Reservation not found" in response.json()["detail"]

    def test_cancel_reservation_missing_api_key(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        reservation_id = res_response.json()["id"]

        response = client.post(f"/reservations/{reservation_id}/cancel")
        assert response.status_code == 401


class TestOrderEndpoints:
    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["total"] == 0
        assert len(data["orders"]) == 0

    def test_get_orders_pagination(self, client, api_key):
        client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 1000},
            headers={"X-API-Key": api_key}
        )

        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "PROD001",
                    "quantity": 10,
                    "idempotency_key": f"idempotency-key-{i}"
                },
                headers={"X-API-Key": api_key}
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"X-API-Key": api_key}
            )

        response_page_1 = client.get("/orders?page=1&size=10")
        assert response_page_1.status_code == 200
        data_page_1 = response_page_1.json()
        assert data_page_1["total"] == 25
        assert len(data_page_1["orders"]) == 10
        assert data_page_1["page"] == 1

        response_page_2 = client.get("/orders?page=2&size=10")
        data_page_2 = response_page_2.json()
        assert len(data_page_2["orders"]) == 10
        assert data_page_2["page"] == 2

        response_page_3 = client.get("/orders?page=3&size=10")
        data_page_3 = response_page_3.json()
        assert len(data_page_3["orders"]) == 5
        assert data_page_3["page"] == 3

    def test_get_orders_invalid_page(self, client):
        response = client.get("/orders?page=0")
        assert response.status_code == 400


class TestIntegrationWorkflow:
    def test_complete_workflow(self, client, api_key):
        # Step 1: Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "PROD001", "initial_stock": 100},
            headers={"X-API-Key": api_key}
        )
        assert sku_response.status_code == 201

        # Step 2: Create Reservation
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PROD001",
                "quantity": 30,
                "idempotency_key": "idempotency-key-1"
            },
            headers={"X-API-Key": api_key}
        )
        assert res_response.status_code == 201
        reservation_id = res_response.json()["id"]

        # Step 3: Confirm Reservation
        conf_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": api_key}
        )
        assert conf_response.status_code == 200
        order_id = conf_response.json()["order_id"]

        # Step 4: Get Orders
        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        orders_data = orders_response.json()
        assert orders_data["total"] == 1
        assert orders_data["orders"][0]["id"] == order_id
