import pytest
import tempfile
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from commerce_service.security import verify_api_token
from fastapi.responses import JSONResponse
from fastapi import HTTPException, status, Depends


def create_test_app(repo):
    app = FastAPI()
    service = CommerceService(repo)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/skus", status_code=201, response_model=SKUResponse)
    async def create_sku(
        request: SKURequest,
        token: str = Depends(verify_api_token),
    ):
        try:
            result = service.create_sku(request.sku, request.initial_stock)
            return SKUResponse(**result)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/stock/adjust", response_model=StockAdjustResponse)
    async def adjust_stock(
        request: StockAdjustRequest,
        token: str = Depends(verify_api_token),
    ):
        try:
            result = service.adjust_stock(request.sku, request.amount)
            return StockAdjustResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/reservations", status_code=201, response_model=ReservationResponse)
    async def create_reservation(
        request: ReservationRequest,
        token: str = Depends(verify_api_token),
    ):
        try:
            reservation, status_code = service.create_reservation(
                request.sku,
                request.quantity,
                request.idempotency_key,
            )
            if status_code == 200:
                return JSONResponse(
                    status_code=200,
                    content=ReservationResponse(**reservation).model_dump(mode="json"),
                )
            return ReservationResponse(**reservation)
        except ValueError as e:
            if "Insufficient stock" in str(e):
                raise HTTPException(status_code=400, detail="Insufficient stock")
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
    async def confirm_reservation(
        id: int,
        token: str = Depends(verify_api_token),
    ):
        try:
            result = service.confirm_reservation(id)
            return ReservationResponse(**result)
        except ValueError as e:
            if "expired" in str(e).lower():
                raise HTTPException(status_code=400, detail="Reservation expired")
            if "PENDING" in str(e):
                raise HTTPException(status_code=400, detail=str(e))
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
    async def cancel_reservation(
        id: int,
        token: str = Depends(verify_api_token),
    ):
        try:
            result = service.cancel_reservation(id)
            return ReservationResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/orders", response_model=OrderListResponse)
    async def get_orders(page: int = 1, size: int = 10):
        try:
            if page < 1:
                page = 1
            if size < 1:
                size = 10

            orders, total = service.get_orders(page, size)
            order_responses = [OrderResponse(**order) for order in orders]

            return OrderListResponse(
                items=order_responses,
                page=page,
                size=size,
                total=total,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return app, service


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def client(temp_db):
    repo = Repository(temp_db)
    app, service = create_test_app(repo)
    return TestClient(app), service


@pytest.fixture
def headers():
    return {"Authorization": "Bearer test-api-key-123"}


def test_health(client):
    test_client, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client, headers):
    test_client, _ = client
    response = test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_create_sku_unauthorized(client):
    test_client, _ = client
    response = test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401 or response.status_code == 403


def test_create_sku_invalid_token(client):
    test_client, _ = client
    response = test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_adjust_stock(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    response = test_client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 10},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 110


def test_adjust_stock_unauthorized(client):
    test_client, _ = client
    response = test_client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 10},
    )
    assert response.status_code == 401 or response.status_code == 403


def test_create_reservation_happy_path(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    response = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 5},
        headers=headers,
    )

    response = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    response1 = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    assert response1.status_code == 201
    data1 = response1.json()
    reservation_id = data1["id"]

    response2 = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["id"] == reservation_id

    response = test_client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 90


def test_confirm_reservation(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    res = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["id"]

    response = test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_not_pending(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    res = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["id"]

    test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )

    response = test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400
    assert "PENDING" in response.json()["detail"]


def test_confirm_reservation_unauthorized(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    res = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["id"]

    response = test_client.post(
        f"/reservations/{reservation_id}/confirm",
    )
    assert response.status_code == 401 or response.status_code == 403


def test_cancel_reservation(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    res = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["id"]

    response = test_client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    response = test_client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers=headers,
    )
    assert response.json()["available_stock"] == 100


def test_get_orders(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    for i in range(3):
        res = test_client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 5,
                "idempotency_key": f"idempotency-{i}",
            },
            headers=headers,
        )
        reservation_id = res.json()["id"]
        test_client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers,
        )

    response = test_client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_get_orders_pagination(client, headers):
    test_client, _ = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    for i in range(15):
        res = test_client.post(
            "/reservations",
            json={
                "sku": "SKU001",
                "quantity": 5,
                "idempotency_key": f"idempotency-{i}",
            },
            headers=headers,
        )
        reservation_id = res.json()["id"]
        test_client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=headers,
        )

    response = test_client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 15
    assert len(data["items"]) == 10

    response = test_client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 5


def test_confirm_reservation_expired(client, headers):
    from datetime import datetime, timedelta, timezone

    test_client, service = client
    test_client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=headers,
    )

    res = test_client.post(
        "/reservations",
        json={
            "sku": "SKU001",
            "quantity": 10,
            "idempotency_key": "idempotency-1",
        },
        headers=headers,
    )
    reservation_id = res.json()["id"]

    conn = service.repo._get_connection()
    cursor = conn.cursor()
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    cursor.execute(
        "UPDATE reservations SET created_at = ? WHERE id = ?",
        (old_time, reservation_id),
    )
    conn.commit()
    conn.close()

    response = test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()

    response = test_client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers=headers,
    )
    assert response.json()["available_stock"] == 100
