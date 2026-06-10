"""FastAPI application for commerce service."""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustmentRequest,
)
from .security import verify_api_key
from .service import ConflictError, NotFoundError, Service


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> Service:
    return Service(db)


# Health check


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}


# SKU endpoints


@app.post("/api/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED, tags=["skus"])
def create_sku(
    sku: SKUCreate,
    _: None = Depends(verify_api_key),
    service: Service = Depends(get_service),
) -> SKUResponse:
    try:
        created = service.create_sku(sku.id, sku.name, sku.stock)
        return SKUResponse.model_validate(created)
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Stock adjustment


@app.post("/api/stock/adjust", response_model=SKUResponse, tags=["stock"])
def adjust_stock(
    request: StockAdjustmentRequest,
    _: None = Depends(verify_api_key),
    service: Service = Depends(get_service),
) -> SKUResponse:
    try:
        updated = service.adjust_stock(request.sku_id, request.delta)
        return SKUResponse.model_validate(updated)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Reservation endpoints


@app.post(
    "/api/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reservations"],
)
def create_reservation(
    request: ReservationCreate,
    _: None = Depends(verify_api_key),
    service: Service = Depends(get_service),
) -> ReservationResponse:
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse.model_validate(reservation)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post(
    "/api/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
    tags=["reservations"],
)
def confirm_reservation(
    reservation_id: str,
    _: None = Depends(verify_api_key),
    service: Service = Depends(get_service),
) -> OrderResponse:
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse.model_validate(order)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post(
    "/api/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    tags=["reservations"],
)
def cancel_reservation(
    reservation_id: str,
    _: None = Depends(verify_api_key),
    service: Service = Depends(get_service),
) -> ReservationResponse:
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Order endpoints


@app.get("/api/orders", response_model=OrderListResponse, tags=["orders"])
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: Service = Depends(get_service),
) -> OrderListResponse:
    try:
        orders, total = service.get_orders(page, page_size)
        return OrderListResponse(
            orders=[OrderResponse.model_validate(o) for o in orders],
            total=total,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
