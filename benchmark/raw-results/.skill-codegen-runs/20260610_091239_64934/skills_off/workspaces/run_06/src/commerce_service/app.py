import os
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    OrderResponse,
    OrderStatus,
    PaginatedOrdersResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
)
from .security import verify_api_key
from .service import CommerceService

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: SKUCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    sku = service.create_sku(payload.sku_code, payload.name, payload.stock_quantity)
    return sku


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    sku = service.adjust_stock(sku_id, payload.adjustment)
    return sku


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation = service.create_reservation(
        payload.sku_id,
        payload.quantity,
        payload.idempotency_key,
    )
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation = service.confirm_reservation(reservation_id)
    return reservation


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation = service.cancel_reservation(reservation_id)
    return reservation


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    orders, total, page_num, size, total_pages = service.get_orders_paginated(page, page_size)
    return {
        "items": [
            OrderResponse(
                id=order.id,
                status=order.status,
                created_at=order.created_at,
            )
            for order in orders
        ],
        "total": total,
        "page": page_num,
        "page_size": size,
        "total_pages": total_pages,
    }
