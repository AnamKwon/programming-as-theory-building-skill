from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status

from commerce_service.models import (
    ErrorResponse,
    HealthResponse,
    OrderResponse,
    OrdersListResponse,
    ReservationConfirm,
    ReservationCreate,
    ReservationResponse,
    SkuCreate,
    SkuResponse,
    StockAdjustment,
)
from commerce_service.repository import Repository
from commerce_service.security import verify_api_key
from commerce_service.service import Service

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service
repository = Repository("commerce.db")
service = Service(repository)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    result = service.health_check()
    return HealthResponse(**result)


@app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SkuCreate,
    _: Annotated[str, Depends(verify_api_key)] = None,
):
    """Create a new SKU."""
    return service.create_sku(request.name, request.price, request.stock)


@app.post("/skus/{sku_id}/stock", response_model=SkuResponse)
async def adjust_stock(
    sku_id: str,
    request: StockAdjustment,
    _: Annotated[str, Depends(verify_api_key)] = None,
):
    """Adjust stock for a SKU."""
    try:
        return service.adjust_stock(sku_id, request.quantity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: ReservationCreate,
    _: Annotated[str, Depends(verify_api_key)] = None,
):
    """Create a reservation for inventory."""
    try:
        return service.reserve(request.sku_id, request.quantity, request.idempotency_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: str,
    request: ReservationConfirm,
    _: Annotated[str, Depends(verify_api_key)] = None,
):
    """Confirm a reservation and create an order."""
    try:
        order_id = service.confirm_reservation(reservation_id)
        return {"order_id": order_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/reservations/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reservation(
    reservation_id: str,
    _: Annotated[str, Depends(verify_api_key)] = None,
):
    """Cancel a reservation."""
    if not service.cancel_reservation(reservation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation not found or already cancelled: {reservation_id}",
        )
    return None


@app.get("/orders", response_model=OrdersListResponse)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """List orders with pagination."""
    return service.list_orders(skip, limit)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """Get order details."""
    try:
        return service.get_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
