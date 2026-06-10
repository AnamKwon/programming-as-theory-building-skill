"""FastAPI application setup and routes."""

import os
from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, CreateSKURequest, AdjustStockRequest, CreateReservationRequest
from .models import ReservationResponse, OrderResponse, PaginatedOrdersResponse, StockAdjustmentResponse
from .service import CommerceService
from .security import verify_api_token


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    sku = service.create_sku(request.sku, request.initial_stock)
    return {"id": sku.id, "sku": sku.sku, "initial_stock": sku.initial_stock}


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    sku = service.adjust_stock(request.sku, request.amount)
    if not sku:
        raise HTTPException(status_code=404, detail="SKU not found")
    return StockAdjustmentResponse(sku=sku.sku, available_stock=sku.available_stock)


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    reservation, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if status_code == 400:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    return ReservationResponse(
        id=reservation.id,
        sku=reservation.sku,
        quantity=reservation.quantity,
        idempotency_key=reservation.idempotency_key,
        status=reservation.status,
        created_at=reservation.created_at,
    )


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    order, status_code = service.confirm_reservation(reservation_id)

    if status_code == 404:
        raise HTTPException(status_code=404, detail="Reservation not found")
    elif status_code == 400:
        raise HTTPException(status_code=400, detail="Reservation expired")

    return order


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    result, status_code = service.cancel_reservation(reservation_id)

    if status_code == 404:
        raise HTTPException(status_code=404, detail="Reservation not found")
    elif status_code == 400:
        raise HTTPException(status_code=400, detail="Reservation is not pending")

    return result


@app.get("/orders")
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    orders, total = service.get_orders_paginated(page, size)

    return PaginatedOrdersResponse(
        orders=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        page=page,
        size=size,
    )
