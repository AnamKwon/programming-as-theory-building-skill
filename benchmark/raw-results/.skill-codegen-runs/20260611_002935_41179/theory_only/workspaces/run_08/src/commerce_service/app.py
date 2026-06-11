"""FastAPI application for Commerce Service."""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from .repository import Database
from .service import CommerceService
from .security import validate_api_token
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
    OrderResponse,
    HealthResponse,
)

app = FastAPI(title="Commerce Service")

db = Database(db_path=":memory:")
db.init_schema()

service = CommerceService(db)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> dict:
    """Health check endpoint. No authentication required."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(validate_api_token),
) -> dict:
    """Create a new SKU with initial stock. Returns 201 Created."""
    sku_id, sku_name, initial_stock = service.create_sku(
        request.sku, request.initial_stock
    )
    return {
        "id": sku_id,
        "sku": sku_name,
        "available_stock": initial_stock,
    }


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(validate_api_token),
) -> dict:
    """Adjust stock level for a SKU. Returns 200 OK with updated stock."""
    new_stock = service.adjust_stock(request.sku, request.amount)

    if new_stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found",
        )

    return {
        "sku": request.sku,
        "adjusted_by": request.amount,
        "new_stock": new_stock,
    }


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(validate_api_token),
) -> ReservationResponse:
    """
    Create a reservation with stock check and idempotency.

    Rule 1: If available stock < quantity, return 400 with "Insufficient stock".
    Rule 2: If idempotency_key exists, return previously saved response without mutating.
    Rule 3: Deduct stock and create reservation with PENDING status.
    """
    success, reservation, error = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if not success:
        if error == "Insufficient stock":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error,
            )

    return reservation


@app.post(
    "/reservations/{reservation_id}/confirm",
    status_code=200,
    response_model=ConfirmReservationResponse,
)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(validate_api_token),
) -> ConfirmReservationResponse:
    """
    Confirm a reservation.

    Rule: Change status from PENDING to CONFIRMED. Create Order. Return 200 OK.
    Expiration Check: If created > 300 seconds ago, set to EXPIRED, restore stock, return 400.
    State Validation: If not PENDING, return 400.
    """
    success, data, error = service.confirm_reservation(reservation_id)

    if not success:
        if "expired" in error.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error,
            )

    res_id, order_id, confirmed_status = data
    return ConfirmReservationResponse(
        reservation_id=res_id,
        order_id=order_id,
        status=confirmed_status,
    )


@app.post(
    "/reservations/{reservation_id}/cancel",
    status_code=200,
    response_model=CancelReservationResponse,
)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(validate_api_token),
) -> CancelReservationResponse:
    """
    Cancel a reservation.

    Rule: Change status to CANCELLED. Restore reserved quantity back to SKU stock.
    State Validation: If not PENDING, return 400.
    """
    success, data, error = service.cancel_reservation(reservation_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    res_id, cancelled_status, restored_stock = data
    return CancelReservationResponse(
        reservation_id=res_id,
        status=cancelled_status,
        restored_stock=restored_stock,
    )


@app.get("/orders", status_code=200, response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10) -> OrderListResponse:
    """
    Get paginated list of orders.

    Query parameters:
    - page: Page number (default 1)
    - size: Page size (default 10)
    """
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    orders, total, page_count = service.get_orders_paginated(page, size)

    return OrderListResponse(
        items=orders,
        total=total,
        page=page,
        size=size,
        pages=page_count,
    )
