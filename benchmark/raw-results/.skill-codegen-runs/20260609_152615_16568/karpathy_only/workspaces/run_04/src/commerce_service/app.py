import os
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, OrderListResponse, OrderResponse, ReservationCancel, ReservationConfirm, ReservationCreate, ReservationResponse, SKUCreate, SKUResponse, StockAdjustment
from .security import verify_api_key
from .service import (
    CommerceService,
    DuplicateReservationError,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {})
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
def create_sku(sku: SKUCreate, db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    service = CommerceService(db)
    existing = service.sku_repo.get_by_code(sku.code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU with code {sku.code} already exists",
        )
    result = service.create_sku(sku.code, sku.name, sku.initial_stock)
    return SKUResponse.from_orm(result)


@app.post("/skus/{sku_id}/stock/adjust", response_model=SKUResponse)
def adjust_stock(
    sku_id: int,
    adjustment: StockAdjustment,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.adjust_stock(sku_id, adjustment.amount)
        return SKUResponse.from_orm(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    reservation: ReservationCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.create_reservation(
            reservation.sku_id,
            reservation.amount,
            reservation.idempotency_key,
        )
        return ReservationResponse.from_orm(result["reservation"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DuplicateReservationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: int,
    _: ReservationConfirm,
    db: Session = Depends(get_db),
    __: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse.from_orm(result["reservation"])
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    _: ReservationCancel,
    db: Session = Depends(get_db),
    __: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse.from_orm(result["reservation"])
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    result = service.list_orders(page, page_size)
    return OrderListResponse(
        items=[OrderResponse.from_orm(order) for order in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )
