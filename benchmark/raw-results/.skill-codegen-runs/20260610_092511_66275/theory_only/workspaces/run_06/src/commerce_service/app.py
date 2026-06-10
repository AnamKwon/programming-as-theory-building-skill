"""FastAPI application."""

import os
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .security import verify_api_key
from .service import CommerceService, CommerceProblem
from . import models as schema

# Database setup
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Health and info


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# SKU endpoints


@app.post("/skus", response_model=schema.SKUResponse, status_code=201)
async def create_sku(
    req: schema.SKUCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        sku = CommerceService(db).create_sku(req.sku_code, req.stock_available)
        return sku
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@app.post("/skus/{sku_id}/adjust-stock", response_model=schema.SKUResponse)
async def adjust_stock(
    sku_id: int,
    req: schema.AdjustStockRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Adjust stock for a SKU."""
    try:
        sku = CommerceService(db).adjust_stock(sku_id, req.quantity_delta)
        return sku
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# Reservation endpoints


@app.post("/reservations", response_model=schema.ReservationResponse, status_code=201)
async def create_reservation(
    req: schema.ReservationRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Create a reservation."""
    try:
        reservation = CommerceService(db).create_reservation(
            req.sku_id, req.quantity, req.idempotency_key, req.ttl_seconds
        )
        return reservation
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@app.post("/reservations/{reservation_id}/confirm", response_model=schema.OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _req: schema.OrderConfirmRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Confirm a reservation and create an order."""
    try:
        _, order = CommerceService(db).confirm_reservation(reservation_id)
        return order
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@app.post("/reservations/{reservation_id}/cancel", response_model=schema.ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Cancel a reservation."""
    try:
        reservation = CommerceService(db).cancel_reservation(reservation_id)
        return reservation
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# Order endpoints


@app.get("/orders/{order_id}", response_model=schema.OrderResponse)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    """Get an order by ID."""
    try:
        order = CommerceService(db).get_order(order_id)
        return order
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@app.get("/orders", response_model=schema.OrderListResponse)
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    try:
        orders, total = CommerceService(db).list_orders(offset, limit)
        return schema.OrderListResponse(
            items=orders,
            total=total,
            offset=offset,
            limit=limit,
        )
    except CommerceProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
