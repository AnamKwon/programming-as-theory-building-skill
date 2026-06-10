from fastapi import FastAPI, Depends, status
from typing import Annotated
from commerce_service import init_db
from commerce_service.models import (
    CreateSKURequest, AdjustStockRequest, CreateReservationRequest,
    ReservationResponse, OrderResponse, OrderListResponse
)
from commerce_service.security import verify_api_token
from commerce_service.service import CommerceService

app = FastAPI()
service = CommerceService()

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    return service.create_sku(request.sku, request.initial_stock)

@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: AdjustStockRequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    return service.adjust_stock(request.sku, request.amount)

@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    token: Annotated[str, Depends(verify_api_token)] = None
) -> ReservationResponse:
    return service.create_reservation(request.sku, request.quantity, request.idempotency_key)

@app.post("/reservations/{id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    id: int,
    token: Annotated[str, Depends(verify_api_token)] = None
) -> OrderResponse:
    return service.confirm_reservation(id)

@app.post("/reservations/{id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_reservation(
    id: int,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    return service.cancel_reservation(id)

@app.get("/orders", status_code=status.HTTP_200_OK)
async def get_orders(page: int = 1, size: int = 10) -> OrderListResponse:
    return service.get_orders(page, size)
