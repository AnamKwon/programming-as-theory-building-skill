from fastapi import FastAPI, HTTPException, status, Depends, Query
from .models import (
    CreateSKURequest, AdjustStockRequest, ReservationRequest,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service")
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key)
) -> dict:
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key)
) -> dict:
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key)
) -> dict:
    try:
        result = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key
        )
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key)
) -> dict:
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not PENDING")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key)
) -> dict:
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1)
) -> dict:
    result = service.get_orders(page, size)
    return result
