from fastapi import FastAPI, HTTPException, Depends, Query, status
from .models import (
    CreateSKURequest,
    CreateReservationRequest,
    AdjustStockRequest,
    HealthResponse,
    ReservationResponse,
    StockResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key


app = FastAPI(title="Commerce Service")
repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key)
):
    """Create a new SKU with initial stock"""
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key)
):
    """Adjust stock level for a SKU"""
    result = service.adjust_stock(request.sku, request.amount)
    if result is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return result


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    """Create a reservation with idempotency key"""
    try:
        result = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key
        )
        if result is None:
            raise HTTPException(status_code=404, detail="SKU not found")
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key)
):
    """Confirm a reservation and create an order"""
    try:
        result = service.confirm_reservation(reservation_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING status" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key)
):
    """Cancel a reservation and restore stock"""
    try:
        result = service.cancel_reservation(reservation_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return result
    except ValueError as e:
        if "not in PENDING status" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1)
):
    """Get paginated list of orders"""
    result = service.get_orders_paginated(page, size)
    return result
