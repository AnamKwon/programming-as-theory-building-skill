"""FastAPI application and endpoints."""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from .models import (
    SKURequest,
    StockAdjustRequest,
    ReservationRequest,
    ReservationResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service API", version="0.1.0")

# Initialize repository and service
repository = Repository()
service = CommerceService(repository)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(request: SKURequest, api_key: str = Depends(verify_api_key)):
    """Create a new SKU with initial stock."""
    result = service.create_sku(request.sku, request.initial_stock)
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )
    return result


@app.post("/stock/adjust")
async def adjust_stock(request: StockAdjustRequest, api_key: str = Depends(verify_api_key)):
    """Adjust stock level for a SKU."""
    result = service.adjust_stock(request.sku, request.amount)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found",
        )
    return result


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationRequest, api_key: str = Depends(verify_api_key)
):
    """Create a new reservation with stock validation and idempotency."""
    reservation, error = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if error:
        if error == "Insufficient stock":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )
        elif error == "SKU not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error,
            )

    return reservation


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int, api_key: str = Depends(verify_api_key)
):
    """Confirm a pending reservation and create an order."""
    result, error = service.confirm_reservation(id)

    if error:
        if error == "Reservation expired":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )
        elif error == "Reservation not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error,
            )

    return result


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int, api_key: str = Depends(verify_api_key)
):
    """Cancel a pending reservation and restore stock."""
    result, error = service.cancel_reservation(id)

    if error:
        if error == "Reservation not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error,
            )

    return result


@app.get("/orders")
async def get_orders(page: int = 1, size: int = 10):
    """Get paginated list of orders."""
    if page < 1 or size < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page and size must be >= 1",
        )
    return service.get_orders(page, size)
