from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from .models import (
    CreateSKURequest,
    CreateSKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key


app = FastAPI(title="Commerce Service")
repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=CreateSKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=AdjustStockResponse)
async def adjust_stock(
    request: AdjustStockRequest, api_key: str = Depends(verify_api_key)
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest, api_key: str = Depends(verify_api_key)
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


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(id: int, api_key: str = Depends(verify_api_key)):
    try:
        result = service.confirm_reservation(id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=CancelReservationResponse)
async def cancel_reservation(id: int, api_key: str = Depends(verify_api_key)):
    try:
        result = service.cancel_reservation(id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    api_key: str = Depends(verify_api_key),
):
    result = service.get_orders(page, size)
    return result
