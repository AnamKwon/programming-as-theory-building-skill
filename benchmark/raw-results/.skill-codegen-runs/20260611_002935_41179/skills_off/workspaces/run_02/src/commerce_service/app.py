import os
from fastapi import FastAPI, Depends, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from commerce_service.models import (
    Base,
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    SKUResponse,
)
from commerce_service.service import CommercService
from commerce_service.security import verify_api_key

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="Commerce Inventory & Order API")


def init_db():
    Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def startup_event():
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED, response_model=SKUResponse)
def create_sku(
    request: CreateSKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommercService(db)
    sku = service.create_sku(request.sku, request.initial_stock)
    return sku


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommercService(db)
    sku = service.adjust_stock(request.sku, request.amount)
    return {
        "sku": sku.sku,
        "available_stock": sku.available_stock,
        "reserved_stock": sku.reserved_stock,
    }


@app.post("/reservations", status_code=status.HTTP_201_CREATED, response_model=ReservationResponse)
def create_reservation(
    request: CreateReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommercService(db)
    reservation = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key,
    )
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommercService(db)
    reservation = service.confirm_reservation(reservation_id)
    return reservation


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommercService(db)
    reservation = service.cancel_reservation(reservation_id)
    return reservation


@app.get("/orders")
def list_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommercService(db)
    orders, total = service.get_orders(page, size)
    return {
        "orders": [OrderResponse.from_orm(order) for order in orders],
        "total": total,
        "page": page,
        "size": size,
    }
