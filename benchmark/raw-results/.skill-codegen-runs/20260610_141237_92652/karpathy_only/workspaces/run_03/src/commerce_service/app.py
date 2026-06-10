from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from src.commerce_service.models import (
    HealthResponse,
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    StockAdjustResponse,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
)
from src.commerce_service.security import verify_api_key
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService

app = FastAPI(title="Commerce Service API")

_repo = Repository(db_path=":memory:")
_service = CommerceService(_repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key)
):
    result = _service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=StockAdjustResponse, status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key)
):
    result = _service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    result = _service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return result


@app.post("/reservations/{id}/confirm", status_code=200)
async def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    result = _service.confirm_reservation(id)
    return result


@app.post("/reservations/{id}/cancel", status_code=200)
async def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    result = _service.cancel_reservation(id)
    return result


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(page: int = 1, size: int = 10):
    result = _service.list_orders(page, size)
    return result
