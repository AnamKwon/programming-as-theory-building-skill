from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from .repository import Repository, get_db
from .service import CommerceService
from .security import verify_api_key
from .models import (
    CreateSkuRequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    SkuResponse,
    AdjustStockResponse,
)
from datetime import datetime

app = FastAPI(title="Commerce Service")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SkuResponse)
async def create_sku(
    request: CreateSkuRequest,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    repo = Repository(db)
    service = CommerceService(repo)
    sku_obj = service.create_sku(request.sku, request.initial_stock)
    return {"sku": sku_obj.sku, "stock": sku_obj.stock}


@app.post("/stock/adjust", response_model=AdjustStockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    repo = Repository(db)
    service = CommerceService(repo)
    sku_obj = service.adjust_stock(request.sku, request.amount)
    return {"sku": sku_obj.sku, "stock": sku_obj.stock}


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    repo = Repository(db)
    service = CommerceService(repo)
    reservation = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return {
        "id": reservation.id,
        "sku": reservation.sku,
        "quantity": reservation.quantity,
        "status": reservation.status,
        "created_at": reservation.created_at,
        "idempotency_key": reservation.idempotency_key,
    }


@app.post("/reservations/{id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    repo = Repository(db)
    service = CommerceService(repo)
    order = service.confirm_reservation(id)
    return {
        "id": order.id,
        "reservation_id": order.reservation_id,
        "sku": order.sku,
        "quantity": order.quantity,
        "created_at": order.created_at,
    }


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    repo = Repository(db)
    service = CommerceService(repo)
    result = service.cancel_reservation(id)
    return result


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db)
):
    repo = Repository(db)
    service = CommerceService(repo)
    orders, total = service.get_orders(page, size)
    return {
        "orders": [
            {
                "id": order.id,
                "reservation_id": order.reservation_id,
                "sku": order.sku,
                "quantity": order.quantity,
                "created_at": order.created_at,
            }
            for order in orders
        ],
        "page": page,
        "size": size,
        "total": total,
    }
