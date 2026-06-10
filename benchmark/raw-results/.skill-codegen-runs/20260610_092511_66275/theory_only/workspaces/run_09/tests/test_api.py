import pytest
import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from commerce_service.repository import Repository
from commerce_service.service import Service
from commerce_service.models import (
    CreateSkuRequest,
    SkuResponse,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
)
from commerce_service.security import get_api_key_dependency
from fastapi import HTTPException, status, Depends, Query


@pytest.fixture(autouse=True)
def setup_test_env():
    original_key = os.environ.get("COMMERCE_API_KEY")
    os.environ["COMMERCE_API_KEY"] = "test-key"
    yield
    if original_key:
        os.environ["COMMERCE_API_KEY"] = original_key
    elif "COMMERCE_API_KEY" in os.environ:
        del os.environ["COMMERCE_API_KEY"]


@pytest.fixture
def client():
    test_repo = Repository("sqlite:///:memory:")
    test_service = Service(test_repo)

    test_app = FastAPI()

    @test_app.get("/health")
    def health_check():
        return {"status": "ok"}

    @test_app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
    def create_sku(
        request: CreateSkuRequest,
        api_key: str = Depends(get_api_key_dependency),
    ):
        return test_service.create_sku(request.name, request.total_stock)

    @test_app.post("/skus/{sku_id}/adjust-stock", response_model=SkuResponse)
    def adjust_stock(
        sku_id: int,
        request: AdjustStockRequest,
        api_key: str = Depends(get_api_key_dependency),
    ):
        from commerce_service.service import SkuNotFoundError
        try:
            return test_service.adjust_stock(sku_id, request.adjustment)
        except SkuNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    @test_app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
    def create_reservation(
        request: CreateReservationRequest,
        api_key: str = Depends(get_api_key_dependency),
    ):
        from commerce_service.service import InsufficientStockError
        try:
            return test_service.create_reservation(request.sku_id, request.quantity, request.idempotency_key)
        except InsufficientStockError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @test_app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
    def confirm_reservation(
        reservation_id: int,
        api_key: str = Depends(get_api_key_dependency),
    ):
        from commerce_service.service import ReservationNotFoundError, ReservationExpiredError, InvalidReservationStateError
        try:
            return test_service.confirm_reservation(reservation_id)
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except ReservationExpiredError as e:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
        except InvalidReservationStateError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @test_app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
    def cancel_reservation(
        reservation_id: int,
        api_key: str = Depends(get_api_key_dependency),
    ):
        from commerce_service.service import ReservationNotFoundError, InvalidReservationStateError
        try:
            return test_service.cancel_reservation(reservation_id)
        except ReservationNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except InvalidReservationStateError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @test_app.get("/orders", response_model=OrderListResponse)
    def list_orders(
        limit: int = Query(10, gt=0, le=100),
        offset: int = Query(0, ge=0),
    ):
        return test_service.get_orders(limit, offset)

    return TestClient(test_app)


@pytest.fixture
def auth_header():
    return {"X-API-Key": "test-key"}


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSkuEndpoints:
    def test_create_sku_success(self, client, auth_header):
        response = client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Widget A"
        assert data["total_stock"] == 100
        assert data["reserved_stock"] == 0

    def test_create_sku_missing_auth(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_auth(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        response = client.post(
            "/skus/1/adjust-stock",
            json={"adjustment": 50},
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["total_stock"] == 150

    def test_adjust_stock_not_found(self, client, auth_header):
        response = client.post(
            "/skus/999/adjust-stock",
            json={"adjustment": 50},
            headers=auth_header,
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["quantity"] == 50

    def test_create_reservation_insufficient_stock(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 150, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent_retry(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        response1 = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        response2 = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_confirm_reservation_success(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        response = client.post(
            "/reservations/1/confirm",
            headers=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    def test_confirm_reservation_not_found(self, client, auth_header):
        response = client.post(
            "/reservations/999/confirm",
            headers=auth_header,
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        response = client.post(
            "/reservations/1/cancel",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_reservation_not_found(self, client, auth_header):
        response = client.post(
            "/reservations/999/cancel",
            headers=auth_header,
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_get_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["orders"] == []

    def test_get_orders_with_data(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        for i in range(3):
            client.post(
                "/reservations",
                json={"sku_id": 1, "quantity": 10, "idempotency_key": f"order-{i}"},
                headers=auth_header,
            )
            client.post(
                f"/reservations/{i+1}/confirm",
                headers=auth_header,
            )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["orders"]) == 3

    def test_get_orders_pagination(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        for i in range(5):
            client.post(
                "/reservations",
                json={"sku_id": 1, "quantity": 10, "idempotency_key": f"order-{i}"},
                headers=auth_header,
            )
            client.post(
                f"/reservations/{i+1}/confirm",
                headers=auth_header,
            )

        response = client.get("/orders?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["orders"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_get_orders_limit_validation(self, client):
        response = client.get("/orders?limit=101")
        assert response.status_code == 422

        response = client.get("/orders?limit=0")
        assert response.status_code == 422

        response = client.get("/orders?offset=-1")
        assert response.status_code == 422


class TestUnauthorizedMutations:
    def test_unauthorized_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
        )
        assert response.status_code == 401

    def test_unauthorized_adjust_stock(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        response = client.post(
            "/skus/1/adjust-stock",
            json={"adjustment": 50},
        )
        assert response.status_code == 401

    def test_unauthorized_create_reservation(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
        )
        assert response.status_code == 401

    def test_unauthorized_confirm_reservation(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        response = client.post("/reservations/1/confirm")
        assert response.status_code == 401

    def test_unauthorized_cancel_reservation(self, client, auth_header):
        client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "order-123"},
            headers=auth_header,
        )
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 401


class TestIntegrationFlow:
    def test_end_to_end_reservation_flow(self, client, auth_header):
        sku_resp = client.post(
            "/skus",
            json={"name": "Widget A", "total_stock": 100},
            headers=auth_header,
        )
        assert sku_resp.status_code == 201

        res_resp = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": "test-order-123"},
            headers=auth_header,
        )
        assert res_resp.status_code == 201
        res_data = res_resp.json()
        assert res_data["status"] == "pending"

        conf_resp = client.post(
            "/reservations/1/confirm",
            headers=auth_header,
        )
        assert conf_resp.status_code == 200
        conf_data = conf_resp.json()
        assert conf_data["status"] == "confirmed"

        orders_resp = client.get("/orders")
        assert orders_resp.status_code == 200
        assert orders_resp.json()["total"] == 1
