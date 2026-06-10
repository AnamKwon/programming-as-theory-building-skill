"""FastAPI application for inventory and order orchestration."""

from fastapi import FastAPI, HTTPException, Query, status

from commerce_service.models import (
    OrderListResponse,
    OrderResponse,
    ReservationCreateRequest,
    ReservationResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
)
from commerce_service.repository import Repository
from commerce_service.security import verify_api_key
from commerce_service.service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

repository = Repository()
service = CommerceService(repository)


@app.get("/health", tags=["Health"])
def health_check():
    """Service health check."""
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED, tags=["SKUs"])
def create_sku(request: SKURequest, _: str = Depends(verify_api_key)):
    """Create a new SKU."""
    try:
        sku = service.create_sku(request.code, request.name)
        return SKUResponse(**sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/stock", tags=["Stock"])
def adjust_stock(
    sku_id: int, request: StockAdjustmentRequest, _: str = Depends(verify_api_key)
):
    """Adjust stock for a SKU."""
    try:
        result = service.adjust_stock(sku_id, request.quantity)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/orders", tags=["Orders"], status_code=status.HTTP_201_CREATED)
def create_order(_: str = Depends(verify_api_key)):
    """Create a new order."""
    order = service.create_order()
    return order


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reservations"],
)
def create_reservation(
    request: ReservationCreateRequest, _: str = Depends(verify_api_key)
):
    """Create a reservation with idempotency."""
    try:
        reservation = service.create_reservation(
            request.order_id,
            request.sku_id,
            request.quantity,
            request.idempotency_key,
            request.expires_in_seconds,
        )
        return ReservationResponse(**reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    tags=["Reservations"],
)
def confirm_reservation(
    reservation_id: int, _: str = Depends(verify_api_key)
):
    """Confirm a pending reservation."""
    try:
        reservation = service.confirm_reservation(reservation_id)
        return ReservationResponse(**reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    tags=["Reservations"],
)
def cancel_reservation(
    reservation_id: int, _: str = Depends(verify_api_key)
):
    """Cancel a reservation."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(**reservation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
def get_order(order_id: int):
    """Get order details."""
    try:
        order = service.get_order(order_id)
        return OrderResponse(**order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/orders", response_model=OrderListResponse, tags=["Orders"])
def list_orders(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    """List orders with pagination."""
    result = service.list_orders(skip, limit)
    return OrderListResponse(**result)
