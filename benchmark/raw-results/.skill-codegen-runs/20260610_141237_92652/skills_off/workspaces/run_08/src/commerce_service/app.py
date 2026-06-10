from datetime import datetime
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    OrderListResponse,
    OrderResponse,
    HealthResponse,
)
from .service import CommerceService
from .security import verify_api_key
from .repository import init_db

app = FastAPI(title="Commerce Inventory & Order API")
init_db()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        sku_id = CommerceService.create_sku(request.sku, request.initial_stock)
        return {
            "id": sku_id,
            "sku": request.sku,
            "initial_stock": request.initial_stock
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        updated_stock = CommerceService.adjust_stock(request.sku, request.amount)
        if updated_stock is None:
            raise HTTPException(status_code=404, detail="SKU not found")
        return {
            "sku": request.sku,
            "updated_stock": updated_stock
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        reservation = CommerceService.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key
        )
        created_at = reservation["created_at"]
        return ReservationResponse(
            id=reservation["id"],
            sku=reservation["sku"],
            quantity=reservation["quantity"],
            status=reservation["status"],
            created_at=created_at,
            idempotency_key=reservation["idempotency_key"]
        )
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(
                status_code=400,
                detail="Insufficient stock"
            )
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    try:
        result = CommerceService.confirm_reservation(id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Reservation not found")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    try:
        result = CommerceService.cancel_reservation(id)
        return result
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Reservation not found")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(page: int = 1, size: int = 10):
    if page < 1:
        page = 1
    if size < 1 or size > 100:
        size = 10

    orders, total = CommerceService.get_orders(page, size)

    items = [
        OrderResponse(
            id=order["id"],
            reservation_id=order["reservation_id"],
            created_at=datetime.fromisoformat(order["created_at"])
            if isinstance(order["created_at"], str)
            else order["created_at"]
        )
        for order in orders
    ]

    return OrderListResponse(
        items=items,
        page=page,
        size=size,
        total=total
    )
