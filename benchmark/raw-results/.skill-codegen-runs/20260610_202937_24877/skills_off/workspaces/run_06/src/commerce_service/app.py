"""FastAPI application and routes."""

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdjustStockRequest,
    Base,
    CreateReservationRequest,
    CreateSKURequest,
    OrderResponse,
    PaginatedOrderResponse,
    ReservationResponse,
    SKUResponse,
    StockResponse,
)
from .repository import Repository
from .security import verify_api_token
from .service import CommerceService

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    sku_model = service.create_sku(request.sku, request.initial_stock)
    return SKUResponse(
        id=sku_model.id,
        sku=sku_model.sku,
        available_stock=sku_model.available_stock,
        created_at=sku_model.created_at,
    )


@app.post("/stock/adjust", response_model=StockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    result = service.adjust_stock(request.sku, request.amount)
    if not result:
        raise HTTPException(status_code=400, detail="SKU not found")
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    reservation, error = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    order, error = service.confirm_reservation(reservation_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return order


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_token),
    service: CommerceService = Depends(get_service),
):
    reservation, error = service.cancel_reservation(reservation_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return reservation


@app.get("/orders", response_model=PaginatedOrderResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    service: CommerceService = Depends(get_service),
):
    orders, total = service.repo.get_orders_paginated(page, size)
    pages = (total + size - 1) // size if total > 0 else 1
    return PaginatedOrderResponse(
        items=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku=order.sku,
                quantity=order.quantity,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
