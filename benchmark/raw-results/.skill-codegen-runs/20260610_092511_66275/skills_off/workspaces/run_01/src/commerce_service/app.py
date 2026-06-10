"""FastAPI application for commerce service."""

import uvicorn
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, status

from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import APIKeyDependency

# Initialize repository and service
repo = Repository()
service = CommerceService(repo)

# FastAPI app
app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    repo.init_db()


# Health check
@app.get("/health")
async def health_check():
    """Service health check."""
    return {"status": "ok"}


# SKU endpoints
@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(payload: SKUCreate, _: APIKeyDependency):
    """Create a new SKU."""
    try:
        sku = service.create_sku(payload.sku_code, payload.qty)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(sku_id: int, payload: StockAdjustment, _: APIKeyDependency):
    """Adjust stock quantity for a SKU."""
    try:
        sku = service.adjust_stock(sku_id, payload.delta)
        return SKUResponse.model_validate(sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Reservation endpoints
@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(payload: ReservationCreate, _: APIKeyDependency):
    """Create a reservation."""
    try:
        reservation = service.create_reservation(
            payload.sku_id, payload.qty, payload.idempotency_key, payload.ttl_seconds
        )
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(reservation_id: int, _: APIKeyDependency):
    """Confirm a reservation and create an order."""
    try:
        reservation, order = service.confirm_reservation(reservation_id)
        return {
            "reservation": ReservationResponse.model_validate(reservation),
            "order": OrderResponse.model_validate(order),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(reservation_id: int, _: APIKeyDependency):
    """Cancel a reservation."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse.model_validate(reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Order endpoints
@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, _: APIKeyDependency):
    """Get order by ID."""
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderResponse.model_validate(order)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    _: APIKeyDependency = None,
):
    """List orders with pagination."""
    try:
        orders, total = service.list_orders(offset, limit)
        return OrderListResponse(
            orders=[OrderResponse.model_validate(o) for o in orders],
            total=total,
            offset=offset,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
