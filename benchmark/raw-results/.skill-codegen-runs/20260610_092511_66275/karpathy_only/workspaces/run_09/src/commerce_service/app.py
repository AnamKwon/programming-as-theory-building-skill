"""FastAPI application and route handlers."""

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
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
    InsufficientStockError,
    ReservationAlreadyProcessedError,
    ReservationExpiredError,
    ReservationNotFoundError,
    Service,
    SKUNotFoundError,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service (would be DI container in larger app)
repository = Repository()
service = Service(repository)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(request: SKURequest, _: str = Depends(verify_api_key)) -> dict:
    """Create a new SKU."""
    result = service.create_sku(request.id, request.name, request.initial_stock)
    return result


@app.get("/skus", response_model=list[SKUResponse])
async def list_skus() -> list[dict]:
    """List all SKUs."""
    return service.list_skus()


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    request: StockAdjustmentRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """Adjust stock for a SKU."""
    try:
        result = service.adjust_stock(sku_id, request.adjustment)
        return result
    except SKUNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationRequest, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    """Create a reservation (idempotent via idempotency_key)."""
    try:
        return service.create_reservation(
            request.sku_id, request.quantity, request.ttl_seconds, request.idempotency_key
        )
    except SKUNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str, _: str = Depends(verify_api_key)
) -> dict:
    """Confirm a reservation and create an order."""
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return {"reservation": reservation, "order": order}
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    except ReservationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ReservationAlreadyProcessedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str, _: str = Depends(verify_api_key)
) -> ReservationResponse:
    """Cancel a reservation and restore stock."""
    try:
        return service.cancel_reservation(reservation_id)
    except ReservationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    except ReservationAlreadyProcessedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)
) -> OrderListResponse:
    """List orders with pagination."""
    orders, total = service.list_orders(limit, offset)

    has_more = (offset + limit) < total
    next_cursor = str(offset + limit) if has_more else None

    return OrderListResponse(orders=orders, cursor=next_cursor, has_more=has_more)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    """Get an order by ID."""
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order
