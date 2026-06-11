from fastapi import FastAPI, Depends, status
from typing import Annotated
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    HealthResponse,
)
from .repository import Database
from .service import CommerceService
from .security import verify_api_token

app = FastAPI(title="Commerce Service API")

db = Database("commerce.db")
service = CommerceService(db)


@app.on_event("startup")
async def startup():
    db.initialize_schema()


APIToken = Annotated[str, Depends(verify_api_token)]


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    token: APIToken,
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: AdjustStockRequest,
    token: APIToken,
):
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    token: APIToken,
):
    result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return result


@app.post("/reservations/{id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    id: int,
    token: APIToken,
):
    result = service.confirm_reservation(id)
    return result


@app.post("/reservations/{id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_reservation(
    id: int,
    token: APIToken,
):
    result = service.cancel_reservation(id)
    return result


@app.get("/orders", status_code=status.HTTP_200_OK)
async def get_orders(
    page: int = 1,
    size: int = 10,
):
    result = service.get_orders_paginated(page, size)
    return result
