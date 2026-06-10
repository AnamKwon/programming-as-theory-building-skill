import os
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from commerce_service.models import Base
from commerce_service.service import (
    Commerce,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    InvalidStateTransitionError,
)
from commerce_service.security import verify_api_key

# Database setup
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


# Request/Response Models
class CreateSKURequest(BaseModel):
    sku_id: str
    name: str
    initial_stock: int = 0


class AdjustStockRequest(BaseModel):
    sku_id: str
    quantity_delta: int


class CreateReservationRequest(BaseModel):
    sku_id: str
    quantity: int
    idempotency_key: str
    ttl_minutes: int = 15


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    state: str
    expires_at: str
    is_new: bool


class ConfirmReservationResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    state: str
    confirmed_at: str | None


class CancelReservationResponse(BaseModel):
    reservation_id: str
    state: str
    cancelled_at: str


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    state: str
    created_at: str
    confirmed_at: str | None
    cancelled_at: str | None


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int


app = FastAPI(title="Commerce Service", version="0.1.0")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus")
def create_sku(req: CreateSKURequest, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        sku = Commerce(db).create_sku(req.sku_id, req.name, req.initial_stock)
        return {"sku_id": sku.id, "name": sku.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
def adjust_stock(req: AdjustStockRequest, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        stock = Commerce(db).adjust_stock(req.sku_id, req.quantity_delta)
        return {"sku_id": stock.sku_id, "quantity": stock.quantity}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(req: CreateReservationRequest, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        result = Commerce(db).reserve(
            sku_id=req.sku_id,
            quantity=req.quantity,
            idempotency_key=req.idempotency_key,
            ttl_minutes=req.ttl_minutes,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(reservation_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        result = Commerce(db).confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(reservation_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    try:
        result = Commerce(db).cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    repo = Repository(db)
    order = repo.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
    return {
        "id": order.id,
        "reservation_id": order.reservation_id,
        "sku_id": order.sku_id,
        "quantity": order.quantity,
        "state": order.state,
        "created_at": order.created_at.isoformat(),
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
    }


@app.get("/orders", response_model=OrderListResponse)
def list_orders(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    repo = Repository(db)
    orders, total = repo.get_orders_paginated(skip, limit)
    items = [
        {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "state": order.state,
            "created_at": order.created_at.isoformat(),
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        }
        for order in orders
    ]
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# Import Repository for use in endpoints
from commerce_service.repository import Repository
