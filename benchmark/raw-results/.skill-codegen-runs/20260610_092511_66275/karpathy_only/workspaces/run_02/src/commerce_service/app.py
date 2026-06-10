import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base,
    OrderSchema,
    ReservationCreateRequest,
    ReservationSchema,
    SKUCreateRequest,
    SKUSchema,
    StockAdjustmentRequest,
)
from .repository import Repository
from .security import validate_api_key
from .service import (
    InsufficientStockError,
    InvalidStateTransitionError,
    OrderAlreadyExistsError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> Service:
    repo = Repository(db)
    return Service(repo)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUSchema, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKUCreateRequest,
    service: Service = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    return service.create_sku(request.sku_code, request.name, request.quantity)


@app.patch("/skus/{sku_id}/stock", response_model=SKUSchema)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    service: Service = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    try:
        return service.adjust_stock(sku_id, request.quantity_delta)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationSchema, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationCreateRequest,
    service: Service = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    try:
        return service.create_reservation(
            sku_id=request.sku_id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.patch("/reservations/{reservation_id}/confirm", response_model=OrderSchema)
async def confirm_reservation(
    reservation_id: int,
    service: Service = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except OrderAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.patch("/reservations/{reservation_id}/cancel", response_model=ReservationSchema)
async def cancel_reservation(
    reservation_id: int,
    service: Service = Depends(get_service),
    _: str = Depends(validate_api_key),
):
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=dict)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: Service = Depends(get_service),
):
    orders, total = service.get_orders(limit=limit, offset=offset)
    return {
        "items": orders,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
