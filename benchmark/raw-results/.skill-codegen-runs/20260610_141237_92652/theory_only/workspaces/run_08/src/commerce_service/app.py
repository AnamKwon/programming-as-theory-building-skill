from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from .models import (
    CreateSKURequest, SKUResponse, StockAdjustRequest, StockAdjustResponse,
    CreateReservationRequest, ReservationResponse, OrderResponse, OrderListResponse
)
from .repository import Repository
from .service import Service
from .security import verify_api_key

app = FastAPI(title="Commerce Service API")

# Global repository and service instances
_repository = Repository(":memory:")
_service = Service(_repository)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(request: CreateSKURequest, api_key: str = Depends(verify_api_key)):
    try:
        result = _service.create_sku(request.sku, request.initial_stock)
        return SKUResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200, response_model=StockAdjustResponse)
async def adjust_stock(request: StockAdjustRequest, api_key: str = Depends(verify_api_key)):
    try:
        result = _service.adjust_stock(request.sku, request.amount)
        if not result:
            raise HTTPException(status_code=404, detail="SKU not found")
        return StockAdjustResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(request: CreateReservationRequest, api_key: str = Depends(verify_api_key)):
    try:
        result = _service.create_reservation(request.sku, request.quantity, request.idempotency_key)
        return ReservationResponse(**result)
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", status_code=200, response_model=OrderResponse)
async def confirm_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    try:
        result = _service.confirm_reservation(reservation_id)
        return OrderResponse(**result)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING state" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=200, response_model=ReservationResponse)
async def cancel_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    try:
        result = _service.cancel_reservation(reservation_id)
        return ReservationResponse(**result)
    except ValueError as e:
        if "not in PENDING state" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10, api_key: str = Depends(verify_api_key)):
    try:
        orders, total = _service.get_orders(page, size)
        return OrderListResponse(
            items=[OrderResponse(**order) for order in orders],
            page=page,
            size=size,
            total=total
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
