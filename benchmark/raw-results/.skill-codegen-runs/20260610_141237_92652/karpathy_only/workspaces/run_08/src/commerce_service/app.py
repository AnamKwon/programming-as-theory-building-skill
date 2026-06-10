from fastapi import FastAPI, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import (
    init_db,
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    OrderListResponse,
    HealthResponse,
)
from .service import CommerceService
from .security import verify_api_token

app = FastAPI(title="Commerce Service")

engine, SessionLocal = init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: SKURequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token)
):
    """Create a new SKU with initial stock."""
    service = CommerceService(db)
    return service.create_sku(request.sku, request.initial_stock)

@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token)
):
    """Adjust stock level for a SKU."""
    service = CommerceService(db)
    return service.adjust_stock(request.sku, request.amount)

@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: ReservationRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token)
):
    """Create a stock reservation."""
    service = CommerceService(db)
    response, status_code = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key
    )
    return response

@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token)
):
    """Confirm a reservation and create an order."""
    service = CommerceService(db)
    return service.confirm_reservation(id)

@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token)
):
    """Cancel a reservation and restore stock."""
    service = CommerceService(db)
    return service.cancel_reservation(id)

@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db)
):
    """List orders with pagination."""
    service = CommerceService(db)
    return service.list_orders(page, size)
