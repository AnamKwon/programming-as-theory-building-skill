"""FastAPI application for commerce service."""

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException

from .models import (
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    ReservationRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
)
from .repository import Repository
from .security import verify_api_key
from .service import (
    CommerceService,
    IdempotencyError,
    InsufficientStockError,
    InvalidReservationStateError,
    ReservationExpiredError,
    ReservationNotFoundError,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service
repository = Repository("commerce.db")
service = CommerceService(repository)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        sku = service.create_sku(request.product_name, request.initial_stock)
        return SKUResponse(
            id=sku.id,
            product_name=sku.product_name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
):
    """Adjust stock levels for a SKU."""
    try:
        sku = service.adjust_stock(sku_id, request.quantity_change)
        return SKUResponse(
            id=sku.id,
            product_name=sku.product_name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key),
):
    """Create a new reservation. Idempotency is guaranteed by idempotency_key."""
    try:
        reservation = service.create_reservation(request.sku_id, request.quantity, request.idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=404, detail=f"SKU {request.sku_id} not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    """Confirm a pending reservation and create an order."""
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Reservation {reservation_id} not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    """Cancel a pending reservation and release reserved inventory."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )
    except ReservationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Reservation {reservation_id} not found")
    except InvalidReservationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = 10,
    cursor: Optional[int] = None,
):
    """List orders with pagination."""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

    orders, next_cursor = service.get_orders(limit, cursor)
    return OrderListResponse(
        orders=[
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                status=order.status,
                created_at=order.created_at,
            )
            for order in orders
        ],
        next_cursor=next_cursor,
    )
