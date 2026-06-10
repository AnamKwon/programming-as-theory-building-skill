"""FastAPI application for Commerce Inventory & Order API."""

from fastapi import FastAPI, HTTPException, status, Depends
from .models import (
    HealthResponse,
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationCreate,
    ReservationResponse,
    ReservationConfirmResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API", version="0.1.0")

repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint - no authentication required."""
    return HealthResponse(status="ok")


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(request: SKUCreate, api_key: str = Depends(verify_api_key)):
    """Create a new SKU with initial stock."""
    return service.create_sku(request)


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(request: StockAdjustRequest, api_key: str = Depends(verify_api_key)):
    """Adjust stock levels for a SKU."""
    return service.adjust_stock(request)


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(request: ReservationCreate, api_key: str = Depends(verify_api_key)):
    """Create a reservation for a SKU with idempotency."""
    try:
        response, is_idempotent = service.create_reservation(request)
        return response
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationConfirmResponse)
async def confirm_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    """Confirm a reservation and create an order."""
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    """Cancel a reservation and restore stock."""
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(page: int = 1, size: int = 10, api_key: str = Depends(verify_api_key)):
    """List orders with pagination."""
    return service.get_orders(page=page, size=size)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
