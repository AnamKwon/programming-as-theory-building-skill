"""FastAPI application."""

from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from .models import (
    SKUCreate, SKUResponse, StockAdjustmentRequest,
    ReservationCreateRequest, ReservationResponse,
    OrderResponse, PaginatedOrderResponse, ErrorResponse
)
from .repository import get_db, init_db
from .service import (
    Service, ReservationExpiredError, InsufficientStockError,
    SKUNotFoundError, ReservationNotFoundError, OrderNotFoundError
)
from .security import verify_api_key


app = FastAPI(title="Commerce Service", version="0.1.0")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# SKU endpoints
@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKUCreate,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Create a new SKU."""
    service = Service(db)
    sku = service.create_sku(code=request.code, name=request.name)
    return sku


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: int, db: Session = Depends(get_db)):
    """Get SKU details."""
    service = Service(db)
    try:
        sku = service.get_sku(sku_id)
        return sku
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Adjust stock for a SKU."""
    service = Service(db)
    try:
        sku = service.adjust_stock(sku_id, request.adjustment)
        return sku
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Reservation endpoints
@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationCreateRequest,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Create a new reservation."""
    service = Service(db)
    try:
        reservation = service.create_reservation(
            sku_id=request.sku_id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key
        )
        return reservation
    except SKUNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    """Get reservation details."""
    service = Service(db)
    try:
        reservation = service.get_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Confirm a reservation and create an order."""
    service = Service(db)
    try:
        order = service.confirm_reservation(reservation_id)
        return order
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """Cancel a reservation."""
    service = Service(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Order endpoints
@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: Session = Depends(get_db)):
    """Get order details."""
    service = Service(db)
    try:
        order = service.get_order(order_id)
        return order
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders", response_model=PaginatedOrderResponse)
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List orders with pagination."""
    service = Service(db)
    items, total = service.list_orders(offset, limit)
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit
    }
