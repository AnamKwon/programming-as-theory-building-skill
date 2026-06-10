from fastapi import FastAPI, Depends
from typing import Optional

from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    StockAdjustResponse,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository
from .service import Service
from .security import verify_api_key

app = FastAPI(title="Commerce Service")

repo = Repository()
service = Service(repo)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest, _: str = Depends(verify_api_key)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: AdjustStockRequest, _: str = Depends(verify_api_key)
):
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest, _: str = Depends(verify_api_key)
):
    result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return result


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    id: int, _: str = Depends(verify_api_key)
):
    result = service.confirm_reservation(id)
    return result


@app.post("/reservations/{id}/cancel", response_model=CancelReservationResponse)
async def cancel_reservation(
    id: int, _: str = Depends(verify_api_key)
):
    result = service.cancel_reservation(id)
    return result


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    result = service.get_orders(page, size)
    return result
