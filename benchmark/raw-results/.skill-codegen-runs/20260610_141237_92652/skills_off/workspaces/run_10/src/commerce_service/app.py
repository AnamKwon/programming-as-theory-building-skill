from fastapi import FastAPI, HTTPException, status, Depends
from typing import Annotated

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    StockAdjustmentResponse,
    OrderListResponse,
    OrderResponse,
)
from .repository import Repository, init_db
from .service import CommerceService
from .security import verify_api_token


app = FastAPI(title="Commerce Service")
repo = Repository()
service = CommerceService(repo)


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: CreateSKURequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    try:
        service.create_sku(request.sku, request.initial_stock)
        return {"sku": request.sku, "initial_stock": request.initial_stock}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return StockAdjustmentResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
def create_reservation(
    request: CreateReservationRequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    try:
        result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return ReservationResponse(**result)
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm")
def confirm_reservation(
    id: int,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    try:
        result = service.confirm_reservation(id)
        return ReservationResponse(**result)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel")
def cancel_reservation(
    id: int,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    try:
        result = service.cancel_reservation(id)
        return ReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
def get_orders(page: int = 1, size: int = 10):
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    orders, total = repo.get_orders(page, size)
    order_responses = [OrderResponse(**order) for order in orders]
    return OrderListResponse(orders=order_responses, page=page, size=size, total=total)
