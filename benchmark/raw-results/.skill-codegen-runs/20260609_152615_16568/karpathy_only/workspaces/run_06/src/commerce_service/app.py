import os
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import models
from .models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    DuplicateReservationError,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> Service:
    return Service(Repository(db))


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    sku = service.create_sku(request.sku_code, request.name, request.initial_stock)
    return sku


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
def adjust_stock(
    sku_id: int,
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        sku = service.adjust_stock(sku_id, request.quantity)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    items = [(item.sku_id, item.quantity) for item in request.items]
    try:
        reservation = service.create_reservation(
            request.idempotency_key, items, request.expiry_minutes
        )
        return reservation
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return order
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=dict)
def list_orders(
    skip: int = 0,
    limit: int = 10,
    service: Service = Depends(get_service),
):
    if limit > 100:
        limit = 100
    orders, total = service.list_orders(skip, limit)
    return {
        "items": orders,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str,
    service: Service = Depends(get_service),
):
    try:
        order = service.get_order(order_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
