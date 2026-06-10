import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce_service.models import Base, SKU, Reservation, Order, ReservationStatus, OrderStatus
from commerce_service.security import verify_api_key
from commerce_service.service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class HealthResponse(BaseModel):
    status: str


class SKURequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    stock: int
    reserved_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    quantity: int = Field(..., description="Positive or negative adjustment")


class ReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
def create_sku(
    request: SKURequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    sku = service.create_sku(request.code, request.stock)
    return sku


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    sku = service.adjust_stock(sku_id, request.quantity)
    return sku


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    request: ReservationRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation = service.reserve(request.sku_id, request.quantity, request.idempotency_key)
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    order = service.confirm_reservation(reservation_id)
    return order


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation = service.cancel_reservation(reservation_id)
    return reservation


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    orders, total = service.list_orders(skip, limit)
    return {
        "items": orders,
        "total": total,
        "skip": skip,
        "limit": limit,
    }
