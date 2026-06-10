from fastapi import FastAPI, HTTPException, status, Depends, Query
from commerce_service.models import (
    CreateSKURequest, AdjustStockRequest, CreateReservationRequest,
    HealthResponse, SKUResponse, ReservationResponse, OrderListResponse, OrderResponse
)
from commerce_service.repository import Database
from commerce_service.service import InventoryService
from commerce_service.security import verify_api_key
from datetime import datetime, timezone


app = FastAPI(title="Commerce Service")
db = Database()
service = InventoryService(db)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(req: CreateSKURequest, _: str = Depends(verify_api_key)):
    try:
        result = service.create_sku(req.sku, req.initial_stock)
        return {"sku": result['sku'], "available_stock": result['available_stock']}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=SKUResponse)
async def adjust_stock(req: AdjustStockRequest, _: str = Depends(verify_api_key)):
    try:
        result = service.adjust_stock(req.sku, req.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(req: CreateReservationRequest, _: str = Depends(verify_api_key)):
    try:
        reservation, status_code = service.reserve_stock(req.sku, req.quantity, req.idempotency_key)
        return {
            "id": reservation['id'],
            "sku": reservation['sku'],
            "quantity": reservation['quantity'],
            "status": reservation['status'],
            "created_at": datetime.fromisoformat(reservation['created_at'])
        }
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=OrderResponse)
async def confirm_reservation(id: int, _: str = Depends(verify_api_key)):
    try:
        order = service.confirm_reservation(id)
        return {
            "id": order['id'],
            "reservation_id": order['reservation_id'],
            "sku": order['sku'],
            "quantity": order['quantity'],
            "created_at": datetime.fromisoformat(order['created_at'])
        }
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", status_code=200)
async def cancel_reservation(id: int, _: str = Depends(verify_api_key)):
    try:
        result = service.cancel_reservation(id)
        return result
    except ValueError as e:
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = Query(1, ge=1), size: int = Query(10, ge=1)):
    orders, total = service.get_orders(page, size)
    return {
        "items": [
            {
                "id": o['id'],
                "reservation_id": o['reservation_id'],
                "sku": o['sku'],
                "quantity": o['quantity'],
                "created_at": datetime.fromisoformat(o['created_at'])
            }
            for o in orders
        ],
        "page": page,
        "size": size,
        "total": total
    }
