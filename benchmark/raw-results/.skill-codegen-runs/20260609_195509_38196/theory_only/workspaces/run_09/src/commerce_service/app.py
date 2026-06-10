"""FastAPI application and routes."""

from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query, status

from .models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    HealthResponse,
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import Repository
from .security import validate_api_key
from .service import (
    CommerceService,
    IdempotencyKeyExistsError,
    InsufficientStockError,
    InvalidStateTransitionError,
    ReservationExpiredError,
    ReservationNotFoundError,
)

# Initialize
repository = Repository()
service = CommerceService(repository)

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


# Health check
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Service health check."""
    return HealthResponse(status="ok")


# SKU endpoints
@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest, x_api_key: Optional[str] = Header(None)
):
    """Create a new SKU."""
    validate_api_key(x_api_key)
    try:
        result = service.create_sku(request.name, request.quantity)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int, request: AdjustStockRequest, x_api_key: Optional[str] = Header(None)
):
    """Adjust stock level for a SKU."""
    validate_api_key(x_api_key)
    try:
        result = service.adjust_stock(sku_id, request.delta)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Reservation endpoints
@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    request: CreateReservationRequest, x_api_key: Optional[str] = Header(None)
):
    """Create a reservation for inventory."""
    validate_api_key(x_api_key)
    try:
        result = service.create_reservation(
            request.sku_id, request.quantity, request.idempotency_key
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IdempotencyKeyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(reservation_id: int):
    """Get a reservation by ID."""
    try:
        result = service.get_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int, x_api_key: Optional[str] = Header(None)
):
    """Confirm a pending reservation."""
    validate_api_key(x_api_key)
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int, x_api_key: Optional[str] = Header(None)
):
    """Cancel a reservation."""
    validate_api_key(x_api_key)
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Order endpoints
@app.get("/orders", response_model=OrderListResponse)
async def list_orders(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    """List orders with pagination."""
    result = service.list_orders(offset, limit)
    return result


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int):
    """Get an order by ID."""
    try:
        result = service.get_order(order_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
