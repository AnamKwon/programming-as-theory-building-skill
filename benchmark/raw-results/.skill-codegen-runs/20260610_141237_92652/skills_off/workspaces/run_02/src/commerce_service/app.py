from fastapi import FastAPI, Depends, status
from .models import (
    HealthResponse,
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key


app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU with initial stock."""
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock levels for a SKU."""
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", status_code=status.HTTP_201_CREATED, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
):
    """Create a new reservation."""
    result = service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    return result


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key),
):
    """Confirm a pending reservation."""
    result = service.confirm_reservation(id)
    return result


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key),
):
    """Cancel a reservation."""
    result = service.cancel_reservation(id)
    return result


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    api_key: str = Depends(verify_api_key),
):
    """Get paginated orders."""
    result = service.get_orders(page, size)
    return result
