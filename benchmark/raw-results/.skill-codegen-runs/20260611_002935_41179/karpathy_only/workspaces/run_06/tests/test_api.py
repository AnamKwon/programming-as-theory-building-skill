import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from commerce_service.repository import Repository
from commerce_service.service import Service
from commerce_service import app as app_module


@pytest.fixture
def test_app():
    from fastapi import FastAPI
    test_app = FastAPI(title="Commerce Service")
    test_repo = Repository(":memory:")
    test_service = Service(test_repo)

    # Re-register endpoints on test app
    from commerce_service.security import verify_api_key
    from commerce_service.models import (
        CreateSKURequest,
        AdjustStockRequest,
        CreateReservationRequest,
        ReservationResponse,
        ConfirmReservationResponse,
    )
    from fastapi import Depends, status

    @test_app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @test_app.post("/skus", status_code=status.HTTP_201_CREATED)
    async def create_sku(
        request: CreateSKURequest,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        return test_service.create_sku(request.sku, request.initial_stock)

    @test_app.post("/stock/adjust")
    async def adjust_stock(
        request: AdjustStockRequest,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        return test_service.adjust_stock(request.sku, request.amount)

    @test_app.post("/reservations", status_code=status.HTTP_201_CREATED)
    async def create_reservation(
        request: CreateReservationRequest,
        api_key: str = Depends(verify_api_key),
    ) -> ReservationResponse:
        return test_service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )

    @test_app.post("/reservations/{reservation_id}/confirm")
    async def confirm_reservation(
        reservation_id: int,
        api_key: str = Depends(verify_api_key),
    ) -> ConfirmReservationResponse:
        return test_service.confirm_reservation(reservation_id)

    @test_app.post("/reservations/{reservation_id}/cancel")
    async def cancel_reservation(
        reservation_id: int,
        api_key: str = Depends(verify_api_key),
    ) -> dict:
        return test_service.cancel_reservation(reservation_id)

    @test_app.get("/orders")
    async def list_orders(page: int = 1, size: int = 10) -> dict:
        return test_service.list_orders(page, size)

    test_app.repo = test_repo
    test_app.service = test_service
    return test_app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


VALID_KEY = "test-key-123"
INVALID_KEY = "invalid-key"


class TestHealth:
    def test_health_no_auth(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUCreation:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU001"
        assert response.json()["stock"] == 100

    def test_create_sku_no_auth(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": INVALID_KEY},
        )
        assert response.status_code == 401


class TestStockAdjustment:
    def test_adjust_stock_increase(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150

    def test_adjust_stock_decrease(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 70


class TestReservation:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 150, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent_retry(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        response1 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        response2 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]
        assert response2.json()["quantity"] == 30

    def test_reservation_no_auth(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
        )
        assert response.status_code == 401


class TestConfirmation:
    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == res_id
        assert data["order_id"] is not None
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 30

    def test_confirm_nonpending_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 400
        assert "not pending" in response.json()["detail"]

    def test_confirm_expired_reservation_fails(self, client, test_app):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        # Manually update timestamp to be more than 300 seconds old
        old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
        conn = test_app.repo._get_connection()
        cursor = conn.__enter__().cursor()
        cursor.execute(
            "UPDATE reservations SET timestamp = ? WHERE id = ?",
            (old_time, res_id),
        )
        conn.__exit__(None, None, None)

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"]


class TestCancellation:
    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"
        assert response.json()["stock_restored"] == 30

    def test_cancel_nonpending_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"X-API-Key": VALID_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key1"},
            headers={"X-API-Key": VALID_KEY},
        )
        res_id = res_response.json()["id"]

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": VALID_KEY},
        )
        assert response.status_code == 400


class TestOrders:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orders_with_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers={"X-API-Key": VALID_KEY},
        )
        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key{i}"},
                headers={"X-API-Key": VALID_KEY},
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": VALID_KEY},
            )

        response1 = client.get("/orders?page=1&size=10")
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) == 10
        assert data1["total"] == 25
        assert data1["page"] == 1

        response2 = client.get("/orders?page=2&size=10")
        data2 = response2.json()
        assert len(data2["items"]) == 10
        assert data2["page"] == 2

        response3 = client.get("/orders?page=3&size=10")
        data3 = response3.json()
        assert len(data3["items"]) == 5
        assert data3["page"] == 3


class TestHappyPath:
    def test_complete_workflow(self, client):
        # Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "PRODUCT-A", "initial_stock": 500},
            headers={"X-API-Key": VALID_KEY},
        )
        assert sku_response.status_code == 201

        # Reserve
        res_response = client.post(
            "/reservations",
            json={"sku": "PRODUCT-A", "quantity": 100, "idempotency_key": "order1"},
            headers={"X-API-Key": VALID_KEY},
        )
        assert res_response.status_code == 201
        res_id = res_response.json()["id"]

        # Confirm
        conf_response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_KEY},
        )
        assert conf_response.status_code == 200
        order_id = conf_response.json()["order_id"]

        # Lookup order
        orders_response = client.get("/orders?page=1&size=10")
        assert orders_response.status_code == 200
        orders = orders_response.json()["items"]
        assert any(o["id"] == order_id for o in orders)
