"""FastAPI application."""

from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    AdjustStockResponse,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderResponse,
    PaginatedOrdersResponse,
)
from .repository import Repository
from .service import CommercService
from .security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API")

repository = Repository()
service = CommercService(repository)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU with initial stock."""
    try:
        sku = service.create_sku(request.sku, request.initial_stock)
        return SKUResponse.model_validate(sku)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=AdjustStockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock levels for a SKU."""
    try:
        new_stock = service.adjust_stock(request.sku, request.amount)
        return AdjustStockResponse(sku=request.sku, new_stock=new_stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a reservation with idempotency."""
    try:
        reservation, is_new = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )

        response = ReservationResponse.model_validate(reservation)

        if is_new:
            return JSONResponse(content=response.model_dump(mode='json'), status_code=201)
        else:
            return JSONResponse(content=response.model_dump(mode='json'), status_code=200)

    except ValueError as e:
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
):
    """Confirm a pending reservation and create an order."""
    try:
        reservation, order = service.confirm_reservation(reservation_id)

        return ConfirmReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            order_id=order.id,
            created_at=reservation.created_at,
        )
    except ValueError as e:
        error_msg = str(e)
        if "Reservation expired" in error_msg:
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "Cannot confirm" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
):
    """Cancel a pending reservation and restore stock."""
    try:
        reservation = service.cancel_reservation(reservation_id)
        return CancelReservationResponse(
            id=reservation.id,
            status=reservation.status,
        )
    except ValueError as e:
        error_msg = str(e)
        if "Cannot cancel" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    api_key: str = Depends(verify_api_key),
):
    """Get paginated orders."""
    try:
        orders, total = service.get_orders_paginated(page, size)
        return PaginatedOrdersResponse(
            items=[OrderResponse.model_validate(order) for order in orders],
            page=page,
            size=size,
            total=total,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
