"""FastAPI application for the commerce service."""

from typing import List

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from . import __version__
from .models import (
    CreateSKURequest,
    ErrorResponse,
    HealthResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKUResponse,
    StockAdjustmentRequest,
)
from .repository import Database
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version=__version__,
)

# Initialize database and service
db = Database("commerce.db")
service = CommerceService(db)


# Health check endpoint (no auth required)
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Service health check."""
    return HealthResponse(status="healthy", version=__version__)


# SKU endpoints
@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Query(None, alias="X-API-Key"),
):
    """Create a new SKU with initial stock inventory."""
    # Verify API key
    if api_key:
        await verify_api_key(api_key)

    try:
        return service.create_sku(
            request.sku_id, request.name, request.price, request.initial_stock
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Inventory endpoints
@app.patch("/inventory/{sku_id}", status_code=status.HTTP_200_OK)
async def adjust_inventory(
    sku_id: str,
    request: StockAdjustmentRequest,
    api_key: str = Query(None, alias="X-API-Key"),
):
    """Adjust inventory stock for a SKU."""
    # Verify API key
    if api_key:
        await verify_api_key(api_key)

    try:
        return service.adjust_stock(sku_id, request.quantity_delta)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Reservation endpoints
@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationRequest,
    api_key: str = Query(None, alias="X-API-Key"),
):
    """Create a reservation for inventory. Idempotency key ensures safe retries."""
    # Verify API key
    if api_key:
        await verify_api_key(api_key)

    try:
        return service.create_reservation(request.sku_id, request.quantity, request.idempotency_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_reservation(
    reservation_id: str,
    api_key: str = Query(None, alias="X-API-Key"),
):
    """Confirm a pending reservation and create an order."""
    # Verify API key
    if api_key:
        await verify_api_key(api_key)

    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_reservation(
    reservation_id: str,
    api_key: str = Query(None, alias="X-API-Key"),
):
    """Cancel a pending reservation and release inventory."""
    # Verify API key
    if api_key:
        await verify_api_key(api_key)

    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Order endpoints
@app.get("/orders", response_model=List[OrderResponse], status_code=status.HTTP_200_OK)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    api_key: str = Query(None, alias="X-API-Key"),
):
    """List orders with pagination."""
    # Verify API key
    if api_key:
        await verify_api_key(api_key)

    orders, _ = service.get_orders(skip, limit)
    return orders


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": "HTTP_ERROR"},
    )
