from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base
from .service import Service
from .security import get_api_key
from .models import SKUCreate, AdjustStockRequest, ReservationRequest
import os

# Setup database
DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite:///./commerce.db"
)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Commerce Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: SKUCreate,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        sku = service.create_sku(request.sku, request.initial_stock)
        return {
            "id": sku.id,
            "sku": sku.sku,
            "stock": sku.stock,
            "created_at": sku.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        sku = service.adjust_stock(request.sku, request.amount)
        return {
            "sku": sku.sku,
            "stock": sku.stock,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
def create_reservation(
    request: ReservationRequest,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        reservation = service.reserve_stock(
            request.sku, request.quantity, request.idempotency_key
        )
        return reservation
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        order = service.confirm_reservation(reservation_id)
        return order
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders")
def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    service = Service(db)
    try:
        result = service.get_orders(page, size)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
