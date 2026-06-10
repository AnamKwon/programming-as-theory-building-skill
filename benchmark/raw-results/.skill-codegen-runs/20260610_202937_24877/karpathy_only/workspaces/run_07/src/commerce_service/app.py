"""FastAPI application with all endpoints."""
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from typing import Annotated

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    OrderResponse,
    HealthResponse,
)
from .repository import Database
from .service import CommerceService
from .security import verify_api_token

app = FastAPI(title="Commerce Service")
db = Database(":memory:")
service = CommerceService(db)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint - no authentication required."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    """Create a new SKU with initial stock."""
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    """Adjust stock level for a SKU."""
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    """Create a reservation."""
    result, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if status_code == 201:
        return JSONResponse(content=result, status_code=201)
    elif status_code == 200:
        return JSONResponse(content=result, status_code=200)
    elif status_code == 404:
        raise HTTPException(status_code=404, detail=result.get("detail", "Not found"))
    else:
        raise HTTPException(status_code=400, detail=result.get("detail", "Bad request"))


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(
    reservation_id: int,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    """Confirm a reservation and create an order."""
    result, status_code = service.confirm_reservation(reservation_id)

    if status_code == 200:
        return JSONResponse(content=result, status_code=200)
    elif status_code == 404:
        raise HTTPException(status_code=404, detail=result.get("detail", "Not found"))
    else:
        raise HTTPException(status_code=400, detail=result.get("detail", "Bad request"))


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: int,
    token: Annotated[str, Depends(verify_api_token)] = None
):
    """Cancel a reservation."""
    result, status_code = service.cancel_reservation(reservation_id)

    if status_code == 200:
        return JSONResponse(content=result, status_code=200)
    elif status_code == 404:
        raise HTTPException(status_code=404, detail=result.get("detail", "Not found"))
    else:
        raise HTTPException(status_code=400, detail=result.get("detail", "Bad request"))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10,
):
    """Get paginated list of orders."""
    result = service.get_orders(page, size)
    return result
