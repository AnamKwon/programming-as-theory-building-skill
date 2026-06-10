from fastapi import FastAPI, Depends
from src.commerce_service.models import (
    CreateSKURequest, AdjustStockRequest, CreateReservationRequest,
    ReservationResponse, OrderListResponse, HealthResponse
)
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService
from src.commerce_service.security import verify_api_token


app = FastAPI(title="Commerce Service")
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    token: str = Depends(verify_api_token)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    token: str = Depends(verify_api_token)
):
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    token: str = Depends(verify_api_token)
):
    result = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key
    )
    return result


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int,
    token: str = Depends(verify_api_token)
):
    result = service.confirm_reservation(id)
    return result


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    token: str = Depends(verify_api_token)
):
    result = service.cancel_reservation(id)
    return result


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    token: str = Depends(verify_api_token)
):
    result = service.get_orders_paginated(page, size)
    return result
