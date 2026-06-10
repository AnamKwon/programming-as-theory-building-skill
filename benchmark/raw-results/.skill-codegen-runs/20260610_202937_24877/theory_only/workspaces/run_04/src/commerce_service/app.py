from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from .models import (
    SKUCreate, SKUResponse, StockAdjustment, ReservationCreate, ReservationResponse,
    OrderListResponse, HealthResponse, ErrorDetail
)
from .repository import Repository, init_db
from .service import CommerceService
from .security import validate_api_key

app = FastAPI(title="Commerce Service")

init_db()
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    payload: SKUCreate,
    api_key: str = Depends(validate_api_key)
):
    return service.create_sku(payload.sku, payload.initial_stock)


@app.post("/stock/adjust", response_model=SKUResponse)
async def adjust_stock(
    payload: StockAdjustment,
    api_key: str = Depends(validate_api_key)
):
    return service.adjust_stock(payload.sku, payload.amount)


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    payload: ReservationCreate,
    api_key: str = Depends(validate_api_key)
):
    result, status_code = service.create_reservation(
        payload.sku, payload.quantity, payload.idempotency_key
    )
    return JSONResponse(status_code=status_code, content=result)


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    id: int,
    api_key: str = Depends(validate_api_key)
):
    return service.confirm_reservation(id)


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int,
    api_key: str = Depends(validate_api_key)
):
    return service.cancel_reservation(id)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    api_key: str = Depends(validate_api_key)
):
    return service.get_orders(page, size)
