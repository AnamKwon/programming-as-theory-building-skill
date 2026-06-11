from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from .models import (
    CreateSkuRequest,
    AdjustStockRequest,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    PaginatedOrdersResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_token

app = FastAPI(title="Commerce Service API")

# Initialize repository and service (singleton)
repo = Repository("commerce.db")
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSkuRequest,
    _: str = Depends(verify_api_token)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_token)
):
    new_stock = service.adjust_stock(request.sku, request.amount)
    if new_stock is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return {"sku": request.sku, "new_stock": new_stock}


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_token)
):
    result, status_code = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key
    )
    if status_code != 201:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))
    return result


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_token)
):
    result, status_code = service.confirm_reservation(reservation_id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))
    return result


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_token)
):
    result, status_code = service.cancel_reservation(reservation_id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))
    return result


@app.get("/orders", status_code=200)
async def get_orders(
    page: int = 1,
    size: int = 10,
    _: str = Depends(verify_api_token)
):
    if page < 1:
        page = 1
    if size < 1:
        size = 10
    result = service.get_orders_paginated(page, size)
    return result
