"""FastAPI application."""

from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    AdjustStockRequest,
    CancelReservationRequest,
    ConfirmReservationRequest,
    CreateReservationRequest,
    CreateSKURequest,
    OrderResponse,
    OrdersListResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import init_db
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Inventory & Order API", version="0.1.0")


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU with initial stock."""
    sku_data = CommerceService.create_sku(request.sku, request.initial_stock)
    return SKUResponse(**sku_data)


@app.post("/stock/adjust", response_model=SKUResponse)
def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock for a SKU."""
    sku_data = CommerceService.adjust_stock(request.sku, request.amount)
    return SKUResponse(**sku_data)


@app.post(
    "/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED
)
def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a reservation with idempotency."""
    reservation = CommerceService.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    return ReservationResponse(**reservation)


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    id: int,
    request: ConfirmReservationRequest = None,
    api_key: str = Depends(verify_api_key),
):
    """Confirm a pending reservation."""
    reservation = CommerceService.confirm_reservation(id)
    return ReservationResponse(**reservation)


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    id: int,
    request: CancelReservationRequest = None,
    api_key: str = Depends(verify_api_key),
):
    """Cancel a pending reservation."""
    reservation = CommerceService.cancel_reservation(id)
    return ReservationResponse(**reservation)


@app.get("/orders", response_model=OrdersListResponse)
def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
):
    """Get orders with pagination."""
    orders, total = CommerceService.get_orders(page, size)
    return OrdersListResponse(
        items=[OrderResponse(**order) for order in orders],
        page=page,
        size=size,
        total=total,
    )
