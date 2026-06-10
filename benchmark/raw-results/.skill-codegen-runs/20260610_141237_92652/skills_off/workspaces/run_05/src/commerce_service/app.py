import os
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import (
    Base,
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    ErrorResponse,
)
from .service import CommerceService
from .security import verify_api_token

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Session:
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
    request: CreateSKURequest, db: Session = Depends(get_db), token: str = Depends(verify_api_token)
):
    try:
        service = CommerceService(db)
        sku = service.create_sku(request)
        return {
            "id": sku.id,
            "sku": sku.sku,
            "available_stock": sku.available_stock,
            "created_at": sku.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest, db: Session = Depends(get_db), token: str = Depends(verify_api_token)
):
    try:
        service = CommerceService(db)
        result = service.adjust_stock(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest, db: Session = Depends(get_db), token: str = Depends(verify_api_token)
):
    try:
        service = CommerceService(db)
        reservation = service.create_reservation(request)
        return reservation
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int, db: Session = Depends(get_db), token: str = Depends(verify_api_token)
):
    try:
        service = CommerceService(db)
        order = service.confirm_reservation(reservation_id)
        return order
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int, db: Session = Depends(get_db), token: str = Depends(verify_api_token)
):
    try:
        service = CommerceService(db)
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ValueError as e:
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
async def get_orders(
    page: int = 1, size: int = 10, db: Session = Depends(get_db), token: str = Depends(verify_api_token)
):
    try:
        service = CommerceService(db)
        result = service.get_orders(page, size)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
