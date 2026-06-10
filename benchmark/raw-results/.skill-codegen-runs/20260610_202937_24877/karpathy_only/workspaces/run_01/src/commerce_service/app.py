"""FastAPI application setup and endpoints."""

from fastapi import FastAPI, Depends, HTTPException

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service")

# Initialize repository and service
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(request: CreateSKURequest, _: str = Depends(verify_api_key)):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(request: AdjustStockRequest, _: str = Depends(verify_api_key)):
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(request: CreateReservationRequest, _: str = Depends(verify_api_key)):
    result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return ReservationResponse(**result)


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(reservation_id: int, _: str = Depends(verify_api_key)):
    result = service.confirm_reservation(reservation_id)
    return result


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(reservation_id: int, _: str = Depends(verify_api_key)):
    result = service.cancel_reservation(reservation_id)
    return ReservationResponse(**result)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10, _: str = Depends(verify_api_key)):
    result = service.get_orders(page, size)
    return OrderListResponse(**result)
