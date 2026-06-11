"""FastAPI application for commerce service."""

from typing import Annotated, Union

from fastapi import FastAPI, Depends, HTTPException, status

from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationCreateRequest,
    ReservationResponse,
    OrderListResponse,
)
from .repository import init_db, Repository
from .service import CommerceService
from .security import verify_api_key


# Initialize database on startup
init_db()

app = FastAPI(title="Commerce Service")

# Global service instance
service = CommerceService()


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: SKUCreate,
    api_key: Annotated[str, Depends(verify_api_key)]
) -> SKUResponse:
    """Create a new SKU with initial stock."""
    result = service.create_sku(request.sku, request.initial_stock)
    return SKUResponse(**result)


@app.post("/stock/adjust")
async def adjust_stock(
    request: StockAdjustRequest,
    api_key: Annotated[str, Depends(verify_api_key)]
) -> StockAdjustResponse:
    """Adjust stock level for a SKU."""
    result = service.adjust_stock(request.sku, request.amount)
    return StockAdjustResponse(**result)


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationCreateRequest,
    api_key: Annotated[str, Depends(verify_api_key)]
) -> Union[ReservationResponse, dict]:
    """Create a reservation with idempotency."""
    response, status_code = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key
    )

    if status_code == 400:
        raise HTTPException(status_code=400, detail=response["detail"])

    # For idempotent responses, still return 201 on creation
    return response


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int,
    api_key: Annotated[str, Depends(verify_api_key)]
) -> dict:
    """Confirm a reservation and create an order."""
    response, status_code = service.confirm_reservation(id)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get("detail", "Error"))

    return response


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    api_key: Annotated[str, Depends(verify_api_key)]
) -> dict:
    """Cancel a reservation and restore stock."""
    response, status_code = service.cancel_reservation(id)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get("detail", "Error"))

    return response


@app.get("/orders")
async def get_orders(
    page: int = 1,
    size: int = 10,
    api_key: Annotated[str, Depends(verify_api_key)] = None
) -> OrderListResponse:
    """Get paginated list of orders."""
    return service.get_orders(page=page, size=size)
