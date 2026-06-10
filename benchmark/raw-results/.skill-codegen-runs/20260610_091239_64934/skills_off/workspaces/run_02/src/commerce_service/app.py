import os
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base
from .repository import Repository
from .service import (
    Service,
    ServiceError,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationAlreadyConfirmedError,
    ReservationExpiredError,
)
from .security import verify_api_key
from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    StockResponse,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> Service:
    repository = Repository(db)
    return Service(repository)


app = FastAPI(title="Commerce Service", version="0.1.0")


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    sku = service.create_sku(request.sku_id, request.name)
    return SKUResponse.model_validate(sku)


@app.post("/stock/{sku_id}/adjust", response_model=StockResponse)
def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        sku = service.adjust_stock(sku_id, request.quantity)
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return StockResponse(
        sku_id=sku.sku_id,
        available=sku.available,
        reserved=sku.reserved,
        total=sku.available + sku.reserved,
    )


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return ReservationResponse.model_validate(reservation)


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        order = service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationAlreadyConfirmedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return OrderResponse.model_validate(order)


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return ReservationResponse.model_validate(reservation)


@app.get("/orders", response_model=dict)
def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    orders, total = service.get_orders(offset, limit)
    return {
        "items": [OrderResponse.model_validate(o) for o in orders],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
