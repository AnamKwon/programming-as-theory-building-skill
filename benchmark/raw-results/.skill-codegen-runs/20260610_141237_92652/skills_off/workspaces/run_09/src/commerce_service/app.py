from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from commerce_service.models import (
    SKURequest, StockAdjustmentRequest, ReservationRequest,
    ReservationResponse, PaginatedOrders
)
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key
from commerce_service.repository import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Commerce Inventory & Order API", lifespan=lifespan)
service = CommerceService()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(request: SKURequest, _: str = Depends(verify_api_key)):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="SKU already exists")
        raise


@app.post("/stock/adjust")
async def adjust_stock(request: StockAdjustmentRequest, _: str = Depends(verify_api_key)):
    result = service.adjust_stock(request.sku, request.amount)
    if result is None:
        raise HTTPException(status_code=400, detail="SKU not found")
    return result


@app.post("/reservations", status_code=201)
async def create_reservation(request: ReservationRequest, _: str = Depends(verify_api_key)):
    reservation, error = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    if error:
        if error == "Insufficient stock":
            raise HTTPException(status_code=400, detail="Insufficient stock")
        elif error == "SKU not found":
            raise HTTPException(status_code=404, detail="SKU not found")
        else:
            raise HTTPException(status_code=400, detail=error)
    return reservation


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(id: int, _: str = Depends(verify_api_key)):
    result, error = service.confirm_reservation(id)
    if error:
        if error == "Reservation expired":
            raise HTTPException(status_code=400, detail="Reservation expired")
        elif error == "Reservation not found":
            raise HTTPException(status_code=404, detail="Reservation not found")
        else:
            raise HTTPException(status_code=400, detail=error)
    return result


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(id: int, _: str = Depends(verify_api_key)):
    result, error = service.cancel_reservation(id)
    if error:
        if error == "Reservation not found":
            raise HTTPException(status_code=404, detail="Reservation not found")
        else:
            raise HTTPException(status_code=400, detail=error)
    return result


@app.get("/orders")
async def get_orders(page: int = 1, size: int = 10, _: str = Depends(verify_api_key)):
    return service.get_orders_paginated(page, size)
