from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from .models import (
    SKURequest, SKUResponse, StockAdjustRequest, StockAdjustResponse,
    ReservationRequest, ReservationResponse, PaginatedOrders,
    HealthResponse
)
from .service import CommerceService
from .security import verify_api_key
from .repository import init_db


app = FastAPI(title="Commerce Service")
service = CommerceService()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKURequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.create_sku(request.sku, request.initial_stock)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.adjust_stock(request.sku, request.amount)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        response, status_code = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key
        )
        if status_code == 200:
            return JSONResponse(content=response.model_dump(mode='json'), status_code=200)
        return response
    except ValueError as e:
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        error_msg = str(e)
        if "expired" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        elif "not in PENDING state" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        error_msg = str(e)
        if "not in PENDING state" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrders)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    api_key: str = Depends(verify_api_key)
):
    try:
        return service.get_orders_paginated(page, size)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
