"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi import FastAPI, Depends, Header, Query, HTTPException, status
from fastapi.testclient import TestClient
from typing import Annotated

from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)


@pytest.fixture
def test_repo(tmp_path):
    """Create fresh repository with file-based database for each test."""
    db_file = tmp_path / "test.db"
    repo = Repository(f"sqlite:///{db_file}")
    repo.init_db()
    return repo


@pytest.fixture
def test_service(test_repo):
    """Create service with test repository."""
    return CommerceService(test_repo)


@pytest.fixture
def test_client(test_repo, test_service):
    """Create test client with a fresh FastAPI app for testing."""
    from fastapi import Header
    app = FastAPI()

    def verify_api_key(x_api_key: str | None = Header(None)) -> str:
        if not x_api_key or x_api_key != VALID_API_KEY:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return x_api_key

    @app.get("/health")
    async def health_check():
        """Service health check."""
        return {"status": "ok"}

    @app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
    async def create_sku(payload: SKUCreate, _: Annotated[str, Depends(verify_api_key)]):
        """Create a new SKU."""
        try:
            sku = test_service.create_sku(payload.sku_code, payload.qty)
            return SKUResponse.model_validate(sku)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
    async def adjust_stock(sku_id: int, payload: StockAdjustment, _: Annotated[str, Depends(verify_api_key)]):
        """Adjust stock quantity for a SKU."""
        try:
            sku = test_service.adjust_stock(sku_id, payload.delta)
            return SKUResponse.model_validate(sku)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
    async def create_reservation(payload: ReservationCreate, _: Annotated[str, Depends(verify_api_key)]):
        """Create a reservation."""
        try:
            reservation = test_service.create_reservation(
                payload.sku_id, payload.qty, payload.idempotency_key, payload.ttl_seconds
            )
            return ReservationResponse.model_validate(reservation)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.post("/reservations/{reservation_id}/confirm")
    async def confirm_reservation(reservation_id: int, _: Annotated[str, Depends(verify_api_key)]):
        """Confirm a reservation and create an order."""
        try:
            reservation, order = test_service.confirm_reservation(reservation_id)
            return {
                "reservation": ReservationResponse.model_validate(reservation),
                "order": OrderResponse.model_validate(order),
            }
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
    async def cancel_reservation(reservation_id: int, _: Annotated[str, Depends(verify_api_key)]):
        """Cancel a reservation."""
        try:
            reservation = test_service.cancel_reservation(reservation_id)
            return ReservationResponse.model_validate(reservation)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.get("/orders/{order_id}", response_model=OrderResponse)
    async def get_order(order_id: int, _: Annotated[str, Depends(verify_api_key)]):
        """Get order by ID."""
        order = test_service.get_order(order_id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        return OrderResponse.model_validate(order)

    @app.get("/orders", response_model=OrderListResponse)
    async def list_orders(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 50,
        _: Annotated[str, Depends(verify_api_key)] = "",
    ):
        """List orders with pagination."""
        try:
            orders, total = test_service.list_orders(offset, limit)
            return OrderListResponse(
                orders=[OrderResponse.model_validate(o) for o in orders],
                total=total,
                offset=offset,
                limit=limit,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return TestClient(app)

VALID_API_KEY = "dev-key-not-for-production"
HEADERS = {"X-API-Key": VALID_API_KEY}
INVALID_HEADERS = {"X-API-Key": "invalid-key"}


class TestHealth:
    """Tests for health endpoint."""

    def test_health_check(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKU:
    """Tests for SKU endpoints."""

    def test_create_sku(self, test_client):
        """Test creating a SKU."""
        response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 100}, headers=HEADERS)
        assert response.status_code == 201
        data = response.json()
        assert data["sku_code"] == "SKU-001"
        assert data["qty_on_hand"] == 100

    def test_create_sku_unauthorized(self, test_client):
        """Test that creating SKU without API key fails."""
        response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 100})
        assert response.status_code == 401

    def test_create_sku_invalid_key(self, test_client):
        """Test that invalid API key is rejected."""
        response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 100}, headers=INVALID_HEADERS)
        assert response.status_code == 401

    def test_create_duplicate_sku(self, test_client):
        """Test that duplicate SKU codes are rejected."""
        test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 100}, headers=HEADERS)
        response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 50}, headers=HEADERS)
        assert response.status_code == 400

    def test_adjust_stock(self, test_client):
        """Test stock adjustment."""
        sku_response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 100}, headers=HEADERS)
        sku_id = sku_response.json()["id"]

        response = test_client.post(f"/skus/{sku_id}/adjust-stock", json={"delta": 50}, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["qty_on_hand"] == 150

    def test_adjust_stock_negative(self, test_client):
        """Test decreasing stock."""
        sku_response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 100}, headers=HEADERS)
        sku_id = sku_response.json()["id"]

        response = test_client.post(f"/skus/{sku_id}/adjust-stock", json={"delta": -30}, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["qty_on_hand"] == 70

    def test_adjust_stock_insufficient(self, test_client):
        """Test that adjustment cannot go negative."""
        sku_response = test_client.post("/skus", json={"sku_code": "SKU-001", "qty": 50}, headers=HEADERS)
        sku_id = sku_response.json()["id"]

        response = test_client.post(f"/skus/{sku_id}/adjust-stock", json={"delta": -100}, headers=HEADERS)
        assert response.status_code == 400


class TestReservation:
    """Tests for reservation endpoints."""

    @pytest.fixture
    def sku(self, test_client):
        """Create a SKU for testing."""
        response = test_client.post("/skus", json={"sku_code": "SKU-TEST", "qty": 500}, headers=HEADERS)
        return response.json()

    def test_create_reservation(self, test_client, sku):
        """Test creating a reservation."""
        response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == sku["id"]
        assert data["qty"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_idempotent(self, test_client, sku):
        """Test idempotent reservation creation."""
        response1 = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        response2 = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        assert response1.json()["id"] == response2.json()["id"]

    def test_create_reservation_insufficient_stock(self, test_client, sku):
        """Test reservation fails with insufficient stock."""
        response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 600,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_confirm_reservation(self, test_client, sku):
        """Test confirming a reservation."""
        res_response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response = test_client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["reservation"]["status"] == "confirmed"
        assert data["order"]["qty"] == 10

    def test_confirm_reservation_idempotent(self, test_client, sku):
        """Test that confirming twice returns same order."""
        res_response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response1 = test_client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        response2 = test_client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        assert response1.json()["order"]["id"] == response2.json()["order"]["id"]

    def test_cancel_reservation(self, test_client, sku):
        """Test cancelling a reservation."""
        res_response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response = test_client.post(f"/reservations/{res_id}/cancel", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_confirmed_fails(self, test_client, sku):
        """Test that cancelling confirmed reservation fails."""
        res_response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "qty": 10,
                "idempotency_key": "idempotency-key-1",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        test_client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        response = test_client.post(f"/reservations/{res_id}/cancel", headers=HEADERS)
        assert response.status_code == 400


class TestOrder:
    """Tests for order endpoints."""

    @pytest.fixture
    def order(self, test_client):
        """Create an order for testing."""
        sku_response = test_client.post("/skus", json={"sku_code": "SKU-ORDER", "qty": 100}, headers=HEADERS)
        sku_id = sku_response.json()["id"]

        res_response = test_client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "qty": 10,
                "idempotency_key": "order-test-key",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        order_response = test_client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)
        return order_response.json()["order"]

    def test_get_order(self, test_client, order):
        """Test retrieving an order."""
        response = test_client.get(f"/orders/{order['id']}", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["id"] == order["id"]

    def test_get_nonexistent_order(self, test_client):
        """Test retrieving nonexistent order."""
        response = test_client.get("/orders/999", headers=HEADERS)
        assert response.status_code == 404

    def test_list_orders(self, test_client, order):
        """Test listing orders."""
        response = test_client.get("/orders?offset=0&limit=50", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert data["total"] >= 1
        assert data["offset"] == 0
        assert data["limit"] == 50

    def test_list_orders_pagination(self, test_client):
        """Test order list pagination."""
        sku_response = test_client.post("/skus", json={"sku_code": "SKU-PAGINATE", "qty": 500}, headers=HEADERS)
        sku_id = sku_response.json()["id"]

        for i in range(10):
            res_response = test_client.post(
                "/reservations",
                json={
                    "sku_id": sku_id,
                    "qty": 5,
                    "idempotency_key": f"pagination-key-{i}",
                    "ttl_seconds": 3600,
                },
                headers=HEADERS,
            )
            res_id = res_response.json()["id"]
            test_client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)

        page1 = test_client.get("/orders?offset=0&limit=5", headers=HEADERS).json()
        page2 = test_client.get("/orders?offset=5&limit=5", headers=HEADERS).json()

        assert len(page1["orders"]) == 5
        assert len(page2["orders"]) == 5
        assert page1["total"] == 10

    def test_unauthorized_operations(self, test_client, order):
        """Test that operations without API key are unauthorized."""
        response = test_client.get(f"/orders/{order['id']}")
        assert response.status_code == 401

        response = test_client.get("/orders?offset=0&limit=50")
        assert response.status_code == 401
