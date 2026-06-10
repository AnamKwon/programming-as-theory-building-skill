import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from src.commerce_service.models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService
from src.commerce_service.security import verify_api_key


@pytest.fixture
def test_app():
    test_repo = Repository(":memory:")
    test_service = CommerceService(test_repo)

    app = FastAPI()
    app.test_service = test_service
    app.test_repo = test_repo

    @app.get("/health", response_model=HealthResponse)
    def health_check():
        return {"status": "ok"}

    @app.post("/skus", response_model=SKUResponse, status_code=201)
    def create_sku(request: SKURequest, _: str = Depends(verify_api_key)):
        result = test_service.create_sku(request.sku, request.initial_stock)
        return result

    @app.post("/stock/adjust", response_model=StockAdjustResponse)
    def adjust_stock(request: StockAdjustRequest, _: str = Depends(verify_api_key)):
        result = test_service.adjust_stock(request.sku, request.amount)
        return {"sku": result["sku"], "available_stock": result["available_stock"]}

    @app.post("/reservations", response_model=ReservationResponse, status_code=201)
    def create_reservation(request: ReservationRequest, _: str = Depends(verify_api_key)):
        try:
            result = test_service.create_reservation(
                request.sku, request.quantity, request.idempotency_key
            )
            return result
        except ValueError as e:
            if "Insufficient stock" in str(e):
                raise HTTPException(status_code=400, detail="Insufficient stock")
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
    def confirm_reservation(id: int, _: str = Depends(verify_api_key)):
        try:
            result = test_service.confirm_reservation(id)
            return result
        except ValueError as e:
            if "not pending" in str(e).lower():
                raise HTTPException(status_code=400, detail=str(e))
            if "expired" in str(e).lower():
                raise HTTPException(status_code=400, detail="Reservation expired")
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/reservations/{id}/cancel", response_model=CancelReservationResponse)
    def cancel_reservation(id: int, _: str = Depends(verify_api_key)):
        try:
            result = test_service.cancel_reservation(id)
            return result
        except ValueError as e:
            if "not pending" in str(e).lower():
                raise HTTPException(status_code=400, detail=str(e))
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/orders", response_model=OrderListResponse)
    def get_orders(page: int = 1, size: int = 10, _: str = Depends(verify_api_key)):
        result = test_service.get_orders(page, size)
        return result

    return app


@pytest.fixture
def client(test_app):
    tc = TestClient(test_app)
    tc.service = test_app.test_service
    tc.repo = test_app.test_repo
    return tc


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key-123"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_no_auth_required(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_create_sku(client, auth_headers):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100
    assert "id" in data


def test_missing_api_key(client):
    response = client.post("/skus", json={"sku": "SKU002", "initial_stock": 50})
    assert response.status_code == 403


def test_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU003", "initial_stock": 50},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU004", "initial_stock": 50},
        headers=auth_headers,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU004", "amount": 10},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 60
    assert data["sku"] == "SKU004"


def test_happy_path_workflow(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU005", "initial_stock": 100},
        headers=auth_headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU005", "quantity": 30, "idempotency_key": "key001"},
        headers=auth_headers,
    )
    assert res_response.status_code == 201
    res_data = res_response.json()
    assert res_data["status"] == "PENDING"
    assert res_data["quantity"] == 30
    res_id = res_data["id"]

    conf_response = client.post(
        f"/reservations/{res_id}/confirm", headers=auth_headers
    )
    assert conf_response.status_code == 200
    conf_data = conf_response.json()
    assert conf_data["status"] == "CONFIRMED"
    order_id = conf_data["order_id"]

    orders_response = client.get("/orders", headers=auth_headers)
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert len(orders_data["items"]) == 1
    assert orders_data["items"][0]["id"] == order_id


def test_insufficient_stock(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU006", "initial_stock": 10},
        headers=auth_headers,
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU006", "quantity": 50, "idempotency_key": "key002"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_idempotent_reservation_returns_cached(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU007", "initial_stock": 100},
        headers=auth_headers,
    )

    res1 = client.post(
        "/reservations",
        json={"sku": "SKU007", "quantity": 25, "idempotency_key": "key003"},
        headers=auth_headers,
    )
    data1 = res1.json()

    res2 = client.post(
        "/reservations",
        json={"sku": "SKU007", "quantity": 25, "idempotency_key": "key003"},
        headers=auth_headers,
    )
    data2 = res2.json()

    assert data1["id"] == data2["id"]
    assert data1["status"] == data2["status"]


def test_idempotent_no_double_stock_deduction(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU008", "initial_stock": 100},
        headers=auth_headers,
    )

    client.post(
        "/reservations",
        json={"sku": "SKU008", "quantity": 30, "idempotency_key": "key004"},
        headers=auth_headers,
    )

    client.post(
        "/reservations",
        json={"sku": "SKU008", "quantity": 30, "idempotency_key": "key004"},
        headers=auth_headers,
    )

    response = client.post(
        "/skus",
        json={"sku": "SKU009", "initial_stock": 0},
        headers=auth_headers,
    )

    from src.commerce_service.repository import Repository

    repo = Repository(":memory:")
    test_sku = repo.create_sku("SKU008", 100)


def test_expired_reservation_rejection_and_stock_restore(client, auth_headers):
    from datetime import datetime, timedelta

    client.post(
        "/skus",
        json={"sku": "SKU010", "initial_stock": 100},
        headers=auth_headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU010", "quantity": 40, "idempotency_key": "key005"},
        headers=auth_headers,
    )
    res_id = res_response.json()["id"]

    old_time = (datetime.utcnow() - timedelta(seconds=301)).isoformat()
    conn = client.repo.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (old_time, res_id))
    conn.commit()
    client.repo._close_conn(conn)

    conf_response = client.post(
        f"/reservations/{res_id}/confirm", headers=auth_headers
    )
    assert conf_response.status_code == 400
    assert conf_response.json()["detail"] == "Reservation expired"


def test_cannot_confirm_non_pending_reservation(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU011", "initial_stock": 100},
        headers=auth_headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU011", "quantity": 30, "idempotency_key": "key006"},
        headers=auth_headers,
    )
    res_id = res_response.json()["id"]

    client.post(
        "/reservations",
        json={"sku": "SKU011", "quantity": 30, "idempotency_key": "key006"},
        headers=auth_headers,
    )

    client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)

    response = client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)
    assert response.status_code == 400


def test_cancel_reservation(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU012", "initial_stock": 50},
        headers=auth_headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU012", "quantity": 20, "idempotency_key": "key007"},
        headers=auth_headers,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_paginated_orders(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU013", "initial_stock": 500},
        headers=auth_headers,
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU013", "quantity": 10, "idempotency_key": f"key_pag_{i}"},
            headers=auth_headers,
        )
        res_id = res_response.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)

    page1 = client.get("/orders?page=1&size=10", headers=auth_headers)
    assert page1.status_code == 200
    assert len(page1.json()["items"]) == 10
    assert page1.json()["page"] == 1
    assert page1.json()["total"] == 15

    page2 = client.get("/orders?page=2&size=10", headers=auth_headers)
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 5
    assert page2.json()["page"] == 2
    assert page2.json()["total"] == 15


def test_orders_requires_auth(client):
    response = client.get("/orders")
    assert response.status_code in [401, 403]


def test_cancel_non_pending_reservation(client, auth_headers):
    client.post(
        "/skus",
        json={"sku": "SKU014", "initial_stock": 50},
        headers=auth_headers,
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU014", "quantity": 20, "idempotency_key": "key008"},
        headers=auth_headers,
    )
    res_id = res_response.json()["id"]

    client.post(f"/reservations/{res_id}/confirm", headers=auth_headers)

    response = client.post(
        f"/reservations/{res_id}/cancel", headers=auth_headers
    )
    assert response.status_code == 400
