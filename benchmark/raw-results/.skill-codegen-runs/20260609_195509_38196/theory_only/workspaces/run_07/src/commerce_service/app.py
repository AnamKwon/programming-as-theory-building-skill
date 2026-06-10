"""FastAPI application and route handlers."""

import os
from fastapi import FastAPI, Depends, HTTPException, status, Header
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base
from .service import InventoryService
from .security import verify_api_key
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


def get_db():
    """Dependency: database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus")
async def create_sku(
    req: CreateSKURequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Create a new SKU with initial stock."""
    try:
        svc = InventoryService(db)
        sku_record = svc.create_sku(req.sku, req.quantity)
        return {
            "sku": sku_record.sku,
            "available": sku_record.available,
            "reserved": sku_record.reserved,
            "total": sku_record.available + sku_record.reserved,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku}/adjust-stock")
async def adjust_stock(
    sku: str,
    req: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Manually adjust stock for a SKU."""
    try:
        svc = InventoryService(db)
        sku_record = svc.adjust_stock(sku, req.delta, req.reason)
        return {
            "sku": sku_record.sku,
            "available": sku_record.available,
            "reserved": sku_record.reserved,
            "total": sku_record.available + sku_record.reserved,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    req: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Create or retrieve a reservation (idempotent by idempotency_key)."""
    try:
        svc = InventoryService(db)
        reservation = svc.reserve_inventory(req.sku, req.quantity, req.idempotency_key)
        return ReservationResponse.from_orm(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Confirm a pending reservation and create an order."""
    try:
        svc = InventoryService(db)
        reservation, order = svc.confirm_reservation(reservation_id)
        return ReservationResponse.from_orm(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Cancel a pending or confirmed reservation."""
    try:
        svc = InventoryService(db)
        reservation = svc.cancel_reservation(reservation_id)
        return ReservationResponse.from_orm(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """List orders with pagination."""
    if page < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_size must be 1-100")
    svc = InventoryService(db)
    orders, total = svc.list_orders(page, page_size)
    return OrderListResponse(
        orders=[OrderResponse.from_orm(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    _: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Get order details by ID."""
    svc = InventoryService(db)
    order = svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")
    return OrderResponse.from_orm(order)
