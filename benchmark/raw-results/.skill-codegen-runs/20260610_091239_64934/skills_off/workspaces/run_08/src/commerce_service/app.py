from fastapi import FastAPI, HTTPException, status, Depends, Query
from commerce_service.models import (
    HealthResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    ConfirmationResponse,
    CancellationResponse,
    OrderListResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(sku: SKUCreate, _: str = Depends(verify_api_key)):
    try:
        result = service.create_sku(sku.sku_id, sku.name, sku.initial_stock)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(sku_id: str, adjustment: StockAdjustment, _: str = Depends(verify_api_key)):
    try:
        result = service.adjust_stock(sku_id, adjustment.delta)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(reservation: ReservationCreate, _: str = Depends(verify_api_key)):
    try:
        result = service.reserve_stock(reservation.sku_id, reservation.quantity, reservation.idempotency_key)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmationResponse)
async def confirm_reservation(reservation_id: str, _: str = Depends(verify_api_key)):
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/reservations/{reservation_id}", response_model=CancellationResponse)
async def cancel_reservation(reservation_id: str, _: str = Depends(verify_api_key)):
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
    result = service.list_orders(limit, offset)
    return result
