"""FastAPI application and HTTP endpoints."""
from typing import Optional

from fastapi import FastAPI, HTTPException, status, Header, Query
from fastapi.responses import JSONResponse

from .models import (
    SkuRequest,
    SkuResponse,
    StockAdjustmentRequest,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    ErrorResponse,
)
from .repository import Database
from .service import CommerceService
from .security import get_api_key_validator

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize database and service
db = Database()
service = CommerceService(db)
api_key_validator = get_api_key_validator()


def require_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    return api_key_validator.validate(x_api_key)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SkuRequest,
    _: str = Header(None, alias="X-API-Key"),
) -> SkuResponse:
    """Create a new SKU."""
    api_key_validator.validate(_)

    result = service.create_sku(request.id, request.name)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU already exists",
        )
    return SkuResponse(**result)


@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: StockAdjustmentRequest,
    _: str = Header(None, alias="X-API-Key"),
) -> dict:
    """Adjust stock quantity for a SKU."""
    api_key_validator.validate(_)

    result = service.adjust_stock(request.sku_id, request.delta)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found",
        )
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationRequest,
    _: str = Header(None, alias="X-API-Key"),
) -> ReservationResponse:
    """Create a reservation for stock."""
    api_key_validator.validate(_)

    result = service.create_reservation(
        request.sku_id,
        request.quantity,
        request.ttl_seconds,
        request.idempotency_key,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU not found or insufficient stock",
        )

    if result.get("is_duplicate"):
        return ReservationResponse(**{k: v for k, v in result.items() if k != "is_duplicate"})

    return ReservationResponse(**result)


@app.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: str,
    _: str = Header(None, alias="X-API-Key"),
) -> dict:
    """Confirm a reservation and create an order."""
    api_key_validator.validate(_)

    result = service.confirm_reservation(reservation_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation not found, already confirmed, or expired",
        )
    return result


@app.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_reservation(
    reservation_id: str,
    _: str = Header(None, alias="X-API-Key"),
) -> dict:
    """Cancel a pending reservation."""
    api_key_validator.validate(_)

    success = service.cancel_reservation(reservation_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation not found or already confirmed",
        )
    return {"reservation_id": reservation_id, "status": "cancelled"}


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    """Look up an order by ID."""
    result = service.get_order(order_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return OrderResponse(**result)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> OrderListResponse:
    """List orders with pagination."""
    result = service.list_orders(offset, limit)
    return OrderListResponse(**result)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": "error"},
    )
