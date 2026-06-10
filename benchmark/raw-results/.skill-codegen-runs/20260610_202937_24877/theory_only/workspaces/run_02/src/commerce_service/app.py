from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderResponse,
    OrdersListResponse,
)
from .repository import Database
from .service import CommerceService
from .security import verify_api_token


db = Database(db_path="commerce.db")
service = CommerceService(db)
app = FastAPI(title="Commerce Inventory & Order API")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest, token: str = Depends(verify_api_token)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return SKUResponse(**result)


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest, token: str = Depends(verify_api_token)
):
    result = service.adjust_stock(request.sku, request.amount)
    return AdjustStockResponse(**result)


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest, token: str = Depends(verify_api_token)
):
    result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return ReservationResponse(**result)


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(
    reservation_id: int, token: str = Depends(verify_api_token)
):
    result = service.confirm_reservation(reservation_id)
    return ConfirmReservationResponse(**result)


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: int, token: str = Depends(verify_api_token)
):
    result = service.cancel_reservation(reservation_id)
    return CancelReservationResponse(**result)


@app.get("/orders", status_code=200)
async def get_orders(page: int = 1, size: int = 10):
    result = service.get_orders(page, size)
    return OrdersListResponse(**result)
