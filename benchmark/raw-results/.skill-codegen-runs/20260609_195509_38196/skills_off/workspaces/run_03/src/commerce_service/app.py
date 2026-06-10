import os
from contextlib import contextmanager
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .security import verify_api_key
from .service import Commerce, ServiceError
from .models import (
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    StockAdjustmentRequest,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> SKUResponse:
    service = Commerce(db)
    try:
        sku = service.create_sku(request.name, request.initial_stock)
        return SKUResponse(**sku)
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.args[0])


@app.post(
    "/skus/{sku_id}/stock",
    response_model=SKUResponse,
)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> SKUResponse:
    service = Commerce(db)
    try:
        sku = service.adjust_stock(sku_id, request.quantity_delta)
        return SKUResponse(**sku)
    except ServiceError as e:
        if "not found" in e.args[0].lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.args[0])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.args[0])


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    request: CreateReservationRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    service = Commerce(db)
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return ReservationResponse(**reservation)
    except ServiceError as e:
        status_code = (
            status.HTTP_400_BAD_REQUEST
            if "not found" not in e.args[0].lower()
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=status_code, detail=e.args[0])


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
)
async def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    service = Commerce(db)
    try:
        reservation = service.confirm_reservation(reservation_id)
        return ReservationResponse(**reservation)
    except ServiceError as e:
        if "not found" in e.args[0].lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.args[0])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.args[0])


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
async def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    service = Commerce(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(**reservation)
    except ServiceError as e:
        if "not found" in e.args[0].lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.args[0])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.args[0])


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    limit: int = 10, cursor: int = None, db: Session = Depends(get_db)
) -> OrderListResponse:
    if limit < 1 or limit > 100:
        limit = 10

    service = Commerce(db)
    result = service.get_orders(limit, cursor)
    return OrderListResponse(
        items=[OrderResponse(**item) for item in result["items"]],
        next_cursor=result["next_cursor"],
    )
