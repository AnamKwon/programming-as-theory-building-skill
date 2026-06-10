from fastapi import FastAPI, Depends, HTTPException, status, Query

from .models import (
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrdersListResponse,
)
from .repository import Database
from .service import CommerceService
from .security import validate_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
db = Database(":memory:")
service = CommerceService(db)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/skus", response_model=SKUResponse)
async def create_sku(
    request: SKURequest,
    _: str = Depends(validate_api_key),
):
    sku = service.create_sku(request.sku, request.name)
    if not sku:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU {request.sku} already exists",
        )
    return SKUResponse(**sku)


@app.post("/api/inventory/adjust", response_model=dict)
async def adjust_inventory(
    request: StockAdjustmentRequest,
    _: str = Depends(validate_api_key),
):
    result = service.adjust_stock(request.sku, request.quantity)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU {request.sku} not found",
        )
    return result


@app.post("/api/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(validate_api_key),
):
    reservation, error = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    if error:
        if "not found" in error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return ReservationResponse(**reservation)


@app.post("/api/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(validate_api_key),
):
    reservation, error = service.confirm_reservation(reservation_id)
    if error:
        if "not found" in error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        if "expired" in error:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return ReservationResponse(**reservation)


@app.post("/api/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(validate_api_key),
):
    reservation, error = service.cancel_reservation(reservation_id)
    if error:
        if "not found" in error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return ReservationResponse(**reservation)


@app.get("/api/orders", response_model=OrdersListResponse)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    orders, total = service.get_orders(skip, limit)
    return OrdersListResponse(
        orders=[OrderResponse(**o) for o in orders],
        total=total,
        skip=skip,
        limit=limit,
    )
