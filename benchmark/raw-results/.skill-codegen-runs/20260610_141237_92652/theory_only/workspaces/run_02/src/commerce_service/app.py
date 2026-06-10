from fastapi import FastAPI, Depends, HTTPException, status
from .models import (
    SKUCreate, StockAdjust, ReservationCreate,
    SKUResponse, ReservationResponse, OrderResponse, HealthResponse,
    OrderListResponse
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API")
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKUCreate,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.create_sku(request.sku, request.initial_stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=SKUResponse)
async def adjust_stock(
    request: StockAdjust,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.adjust_stock(request.sku, request.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationCreate,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.confirm_reservation(id)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=dict)
async def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.cancel_reservation(id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    return service.get_orders(page, size)
