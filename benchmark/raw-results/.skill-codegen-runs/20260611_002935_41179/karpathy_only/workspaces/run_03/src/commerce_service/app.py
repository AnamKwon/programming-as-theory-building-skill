from fastapi import FastAPI, HTTPException, Depends, status, Query
from commerce_service.models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    StockAdjustResponse,
    HealthResponse,
)
from commerce_service.repository import Database
from commerce_service.service import CommerceService
from commerce_service.security import validate_api_key

app = FastAPI(title="Commerce Service")
db = Database()
service = CommerceService(db)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(validate_api_key)
):
    try:
        service.create_sku(request.sku, request.initial_stock)
        return {"sku": request.sku, "initial_stock": request.initial_stock}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(validate_api_key)
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(validate_api_key)
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


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(validate_api_key)
):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        if "status" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        if "expired" in error_msg:
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(validate_api_key)
):
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        if "status" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    result = service.get_orders(page, size)
    return result
