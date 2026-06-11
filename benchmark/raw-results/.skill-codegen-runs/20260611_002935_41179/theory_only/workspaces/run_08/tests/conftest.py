"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient
from commerce_service.repository import Database
from commerce_service.service import CommerceService
from commerce_service.security import VALID_API_TOKEN
from fastapi import FastAPI, Depends, HTTPException, status

from commerce_service.models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
    OrderResponse,
    HealthResponse,
)
from commerce_service.security import validate_api_token


@pytest.fixture
def app_with_fresh_db():
    """Create a fresh FastAPI app with a fresh in-memory database for each test."""
    # Create a new app and fresh database for this test
    test_app = FastAPI(title="Commerce Service Test")
    test_db = Database(db_path=":memory:")
    test_db.init_schema()
    test_service = CommerceService(test_db)

    @test_app.get("/health", response_model=HealthResponse)
    async def health_check() -> dict:
        return {"status": "ok"}

    @test_app.post("/skus", status_code=201)
    async def create_sku(
        request: CreateSKURequest,
        _: str = Depends(validate_api_token),
    ) -> dict:
        sku_id, sku_name, initial_stock = test_service.create_sku(
            request.sku, request.initial_stock
        )
        return {
            "id": sku_id,
            "sku": sku_name,
            "available_stock": initial_stock,
        }

    @test_app.post("/stock/adjust", status_code=200)
    async def adjust_stock(
        request: AdjustStockRequest,
        _: str = Depends(validate_api_token),
    ) -> dict:
        new_stock = test_service.adjust_stock(request.sku, request.amount)

        if new_stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        return {
            "sku": request.sku,
            "adjusted_by": request.amount,
            "new_stock": new_stock,
        }

    @test_app.post("/reservations", status_code=201, response_model=ReservationResponse)
    async def create_reservation(
        request: CreateReservationRequest,
        _: str = Depends(validate_api_token),
    ) -> ReservationResponse:
        success, reservation, error = test_service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )

        if not success:
            if error == "Insufficient stock":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient stock",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error,
                )

        return reservation

    @test_app.post(
        "/reservations/{reservation_id}/confirm",
        status_code=200,
        response_model=ConfirmReservationResponse,
    )
    async def confirm_reservation(
        reservation_id: int,
        _: str = Depends(validate_api_token),
    ) -> ConfirmReservationResponse:
        success, data, error = test_service.confirm_reservation(reservation_id)

        if not success:
            if "expired" in error.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reservation expired",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error,
                )

        res_id, order_id, confirmed_status = data
        return ConfirmReservationResponse(
            reservation_id=res_id,
            order_id=order_id,
            status=confirmed_status,
        )

    @test_app.post(
        "/reservations/{reservation_id}/cancel",
        status_code=200,
        response_model=CancelReservationResponse,
    )
    async def cancel_reservation(
        reservation_id: int,
        _: str = Depends(validate_api_token),
    ) -> CancelReservationResponse:
        success, data, error = test_service.cancel_reservation(reservation_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error,
            )

        res_id, cancelled_status, restored_stock = data
        return CancelReservationResponse(
            reservation_id=res_id,
            status=cancelled_status,
            restored_stock=restored_stock,
        )

    @test_app.get("/orders", status_code=200, response_model=OrderListResponse)
    async def get_orders(page: int = 1, size: int = 10) -> OrderListResponse:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total, page_count = test_service.get_orders_paginated(page, size)

        return OrderListResponse(
            items=orders,
            total=total,
            page=page,
            size=size,
            pages=page_count,
        )

    return test_app, test_service


@pytest.fixture
def client(app_with_fresh_db):
    """Create a test client for each test."""
    app, _ = app_with_fresh_db
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create authorization headers with valid API token."""
    return {"X-API-Token": VALID_API_TOKEN}


@pytest.fixture
def service(app_with_fresh_db):
    """Create a service instance for each test."""
    _, service = app_with_fresh_db
    return service
