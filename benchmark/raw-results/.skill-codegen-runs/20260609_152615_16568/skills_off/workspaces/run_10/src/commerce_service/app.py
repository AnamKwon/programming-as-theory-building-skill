import os
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, status
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    InvalidStateTransitionError,
)
from commerce_service.security import verify_api_key
from commerce_service.models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderPage,
    ErrorResponse,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repository = Repository(db)
    return CommerceService(repository)


app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)

init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: SKUCreate,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.create_sku(payload.sku_code)
        return sku
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/skus/{sku_id}/adjust-stock",
    response_model=SKUResponse,
)
async def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.adjust_stock(sku_id, payload.delta)
        return sku
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    payload: ReservationCreate,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            payload.sku_id,
            payload.quantity,
            payload.idempotency_key,
        )
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=OrderResponse,
)
async def confirm_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        _, order = service.confirm_reservation(reservation_id)
        return order
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
async def cancel_reservation(
    reservation_id: int,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderPage)
async def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_service),
):
    offset = (page - 1) * limit
    orders, total = service.list_orders(offset, limit)
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "orders": orders,
    }


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    service: CommerceService = Depends(get_service),
):
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return order
