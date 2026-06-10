from fastapi import FastAPI, Depends, HTTPException, status, Query
from commerce_service.models import (
    CreateSKURequest,
    CreateSKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from commerce_service.repository import SQLiteRepository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_token

app = FastAPI(title="Commerce Service")
repository = SQLiteRepository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=CreateSKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest, token: str = Depends(verify_api_token)
):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=AdjustStockResponse)
async def adjust_stock(
    request: AdjustStockRequest, token: str = Depends(verify_api_token)
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest, token: str = Depends(verify_api_token)
):
    try:
        result = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(id: int, token: str = Depends(verify_api_token)):
    try:
        result = service.confirm_reservation(id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(id: int, token: str = Depends(verify_api_token)):
    try:
        result = service.cancel_reservation(id)
        return result
    except ValueError as e:
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100)
):
    result = service.get_orders(page, size)
    return result
