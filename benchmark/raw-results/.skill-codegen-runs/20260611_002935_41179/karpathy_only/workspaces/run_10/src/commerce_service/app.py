"""FastAPI application."""

from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    AdjustStockRequest,
    AdjustStockResponse,
    ConfirmReservationResponse,
    CreateReservationRequest,
    CreateSKURequest,
    ErrorResponse,
    OrderResponse,
    OrdersListResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import Database
from .security import verify_api_token
from .service import CommerceService

app = FastAPI(title="Commerce Service API")

db = Database()
service = CommerceService(db)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest, api_key: str = Depends(verify_api_token)
):
    """Create a new SKU with initial stock."""
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=AdjustStockResponse)
async def adjust_stock(
    request: AdjustStockRequest, api_key: str = Depends(verify_api_token)
):
    """Adjust stock levels for a SKU."""
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest, api_key: str = Depends(verify_api_token)
):
    """Create a reservation for a SKU."""
    try:
        result = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        return {
            "id": result["id"],
            "sku": result["sku"],
            "quantity": result["quantity"],
            "status": result["status"],
            "created_at": datetime.fromisoformat(result["created_at"]),
        }
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    id: int, api_key: str = Depends(verify_api_token)
):
    """Confirm a reservation and create an order."""
    try:
        result = service.confirm_reservation(id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int, api_key: str = Depends(verify_api_token)
):
    """Cancel a reservation and restore stock."""
    try:
        result = service.cancel_reservation(id)
        return {
            "id": result["id"],
            "sku": result["sku"],
            "quantity": result["quantity"],
            "status": result["status"],
            "created_at": datetime.fromisoformat(result["created_at"]),
        }
    except ValueError as e:
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrdersListResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
):
    """Get paginated orders."""
    orders, total = service.get_orders(page, size)
    return {
        "orders": [
            {
                "id": order["id"],
                "reservation_id": order["reservation_id"],
                "created_at": datetime.fromisoformat(order["created_at"]),
            }
            for order in orders
        ],
        "page": page,
        "size": size,
        "total": total,
    }
