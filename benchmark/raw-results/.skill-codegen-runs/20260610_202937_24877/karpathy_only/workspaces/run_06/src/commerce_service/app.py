import os
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import (
    Base, SKUCreate, StockAdjustment, ReservationCreate,
    ReservationResponse, OrderResponse, OrderList
)
from .security import get_api_key
from .service import CommerceService

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Inventory & Order API", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    payload: SKUCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Create a new SKU with initial stock."""
    try:
        service = CommerceService(db)
        sku = service.create_sku(payload.sku, payload.initial_stock)
        return {
            "id": sku.id,
            "sku": sku.sku,
            "initial_stock": sku.initial_stock,
            "available_stock": sku.available_stock,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200)
def adjust_stock(
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Adjust stock level for a SKU."""
    try:
        service = CommerceService(db)
        sku = service.adjust_stock(payload.sku, payload.amount)
        return {
            "sku": sku.sku,
            "available_stock": sku.available_stock,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
def create_reservation(
    payload: ReservationCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> ReservationResponse:
    """Create a reservation with idempotency."""
    try:
        service = CommerceService(db)
        reservation = service.create_reservation(
            payload.sku,
            payload.quantity,
            payload.idempotency_key,
        )
        return reservation
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> OrderResponse:
    """Confirm a reservation and create an order."""
    try:
        service = CommerceService(db)
        order = service.confirm_reservation(reservation_id)
        return order
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Cancel a reservation and restore stock."""
    try:
        service = CommerceService(db)
        reservation = service.cancel_reservation(reservation_id)
        return {
            "id": reservation.id,
            "status": reservation.status,
            "sku": reservation.sku,
            "quantity": reservation.quantity,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> OrderList:
    """Get paginated orders."""
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    service = CommerceService(db)
    orders, total = service.get_orders_paginated(page, size)
    return OrderList(
        page=page,
        size=size,
        total=total,
        orders=[OrderResponse.model_validate(order) for order in orders],
    )
