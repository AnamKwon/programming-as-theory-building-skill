"""FastAPI application."""

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from . import __version__
from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationRequest,
    CancelReservationRequest,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import get_api_key


app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version=__version__,
)

# Global repository and service instances
_repo = Repository()
_service = CommerceService(_repo)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)


@app.post("/skus", response_model=SKUResponse)
async def create_sku(request: CreateSKURequest, _: str = Depends(get_api_key)):
    """Create a new SKU."""
    return _service.create_sku(request)


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: str):
    """Get SKU details."""
    return _service.get_sku(sku_id)


@app.post("/stock/adjust")
async def adjust_stock(request: AdjustStockRequest, _: str = Depends(get_api_key)):
    """Adjust stock quantity for a SKU."""
    return _service.adjust_stock(request)


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest, _: str = Depends(get_api_key)
):
    """Create a new reservation.

    The idempotency_key ensures that retried requests with the same key
    return the same reservation instead of creating duplicates.
    """
    return _service.create_reservation(request)


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str, _: str = Depends(get_api_key)
):
    """Confirm a pending reservation.

    Confirming reserves stock and creates an order. The reservation must not
    be expired. Confirming an already-confirmed reservation is idempotent.
    """
    return _service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str, _: str = Depends(get_api_key)
):
    """Cancel a pending reservation.

    Cancelling releases the reservation without reserving stock.
    Cannot cancel already-confirmed reservations.
    """
    return _service.cancel_reservation(reservation_id)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, _: str = Depends(get_api_key)):
    """Get order details."""
    return _service.get_order(order_id)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: str = Depends(get_api_key),
):
    """List orders with pagination.

    Returns orders in reverse chronological order (newest first).
    """
    return _service.list_orders(page=page, page_size=page_size)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": None,
        },
    )
