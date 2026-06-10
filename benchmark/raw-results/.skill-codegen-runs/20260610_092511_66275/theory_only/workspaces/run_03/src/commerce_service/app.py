from contextlib import contextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Annotated

from commerce_service.models import Base
from commerce_service.repository import Repository
from commerce_service.service import (
    Service,
    ServiceError,
    InsufficientStockError,
    ReservationExpiredError,
    ReservationNotFoundError,
    InvalidStateTransitionError,
)
from commerce_service.models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    SKUResponse,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from commerce_service.security import verify_api_key

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


def get_service(db: Session = Depends(get_db)) -> Service:
    repo = Repository(db)
    return Service(repo)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus")
async def create_sku(
    req: CreateSKURequest,
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    try:
        result = service.create_sku(req.code, req.name, req.initial_stock)
        return SKUResponse(**result)
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/skus/{sku_code}/adjust")
async def adjust_stock(
    sku_code: str,
    req: AdjustStockRequest,
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    try:
        result = service.adjust_stock(sku_code, req.quantity)
        return SKUResponse(**result)
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations")
async def create_reservation(
    req: CreateReservationRequest,
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    try:
        result = service.create_reservation(req.sku_code, req.quantity, req.idempotency_key)
        return ReservationResponse(**result)
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse(**result)
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    _: Annotated[str, Depends(verify_api_key)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    service: Service = Depends(get_service),
):
    result = service.list_orders(page, page_size)
    return OrderListResponse(**result)


@app.post("/orders", response_model=OrderResponse)
async def create_order(
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    result = service.create_order()
    return OrderResponse(**result)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    _: Annotated[str, Depends(verify_api_key)],
    service: Service = Depends(get_service),
):
    try:
        result = service.get_order(order_id)
        return OrderResponse(**result)
    except ServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
