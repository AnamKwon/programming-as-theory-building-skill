from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, CreateSKURequest, AdjustStockRequest, CreateReservationRequest
from .models import SKUResponse, ReservationResponse, OrderResponse, OrderListResponse
from .repository import Repository
from .service import (
    Service,
    InsufficientStockError,
    ReservationExpiredError,
    IdempotencyError,
    InvalidStateError,
)
from .security import verify_api_key

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_repository(db: Session = Depends(get_db)):
    return Repository(db)


def get_service(repo: Repository = Depends(get_repository)):
    return Service(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        sku = service.create_sku(request.sku_id, request.quantity)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        sku = service.adjust_stock(sku_id, request.adjustment)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.create_reservation(
            sku_id=request.sku_id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
        )
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except IdempotencyError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@app.delete("/reservations/{reservation_id}", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    orders, next_cursor = service.list_orders(limit=limit, cursor=cursor)
    return OrderListResponse(
        orders=[OrderResponse.model_validate(order) for order in orders],
        next_cursor=next_cursor,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    _: str = Depends(verify_api_key),
    service: Service = Depends(get_service),
):
    try:
        order = service.get_order(order_id)
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
