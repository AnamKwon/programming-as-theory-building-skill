import os
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import (
    Base,
    CreateSKURequest,
    StockAdjustmentRequest,
    CreateReservationRequest,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import get_api_key

# Database setup
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    repo = Repository(db)
    return CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", message="Service is operational")


@app.post("/skus")
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.create_sku(request.name, request.price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: StockAdjustmentRequest,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.adjust_stock(request.sku_id, request.quantity_change)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations")
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.create_reservation(
            request.sku_id,
            request.quantity,
            request.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/orders")
async def create_order(
    _: str = Depends(get_api_key),
    service: CommerceService = Depends(get_service),
):
    return service.create_order()


@app.get("/orders")
async def list_orders(
    skip: int = 0,
    limit: int = 10,
    service: CommerceService = Depends(get_service),
):
    if skip < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Invalid pagination parameters")
    return service.list_orders(skip, limit)


@app.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
):
    try:
        return service.get_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
