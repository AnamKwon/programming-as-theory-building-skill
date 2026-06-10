"""FastAPI application for commerce service."""

from fastapi import Depends, FastAPI, HTTPException, status

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustment,
)
from .repository import SessionLocal, init_db, Repository
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

init_db()


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db=Depends(get_db)) -> CommerceService:
    """Get service instance."""
    return CommerceService(Repository(db))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(
    request: SKUCreate,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new SKU."""
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust", response_model=SKUResponse)
async def adjust_stock(
    request: StockAdjustment,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Adjust stock for a SKU."""
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: ReservationCreate,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Create a new reservation."""
    return service.create_reservation(request.sku, request.quantity, request.idempotency_key)


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Confirm a reservation."""
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Cancel a reservation."""
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    """Get paginated orders."""
    orders, total = service.get_orders(page, size)
    return OrderListResponse(orders=orders, page=page, size=size, total=total)
