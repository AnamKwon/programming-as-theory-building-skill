from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse

from .models import (
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    ReservationRequest,
    ReservationResponse,
    ReservationConfirmRequest,
    OrderResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository(db_path="commerce.db")
service = CommerceService(repo)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKURequest,
    api_key: str = Depends(verify_api_key),
) -> SKUResponse:
    """Create a new SKU."""
    result = service.create_sku(request.sku, request.name, request.initial_stock)
    return SKUResponse(**result)


@app.post("/stock/adjust", response_model=dict, status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: StockAdjustmentRequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Adjust stock for a SKU."""
    result = service.adjust_stock(request.sku, request.delta)
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationRequest,
    api_key: str = Depends(verify_api_key),
) -> ReservationResponse:
    """Create a reservation for a SKU."""
    result = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key,
        request.ttl_seconds,
    )
    return ReservationResponse(**result)


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse, status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: str,
    request: ReservationConfirmRequest,
    api_key: str = Depends(verify_api_key),
) -> OrderResponse:
    """Confirm a reservation, converting it to an order."""
    result = service.confirm_reservation(reservation_id, request.idempotency_key)
    return OrderResponse(**result)


@app.post("/reservations/{reservation_id}/cancel", response_model=dict, status_code=status.HTTP_200_OK)
async def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Cancel a reservation."""
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(offset: int = 0, limit: int = 10) -> OrderListResponse:
    """List orders with pagination."""
    result = service.list_orders(offset, limit)
    return OrderListResponse(**result)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    """Get order details."""
    result = service.get_order(order_id)
    return OrderResponse(**result)
