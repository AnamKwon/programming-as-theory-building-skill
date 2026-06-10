"""FastAPI application and endpoints."""

from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    OrderResponse,
    ErrorResponse,
)
from .repository import Repository
from .service import Service
from .security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API", version="0.1.0")

# Initialize repository and service
repo = Repository()
service = Service(repo)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Create a new SKU with initial stock."""
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", status_code=status.HTTP_200_OK)
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Adjust stock level for a SKU."""
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
) -> ReservationResponse:
    """Create a reservation with idempotency support."""
    result = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    return result


@app.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Confirm a reservation and create an order."""
    result = service.confirm_reservation(reservation_id)
    return result


@app.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Cancel a reservation and restore stock."""
    result = service.cancel_reservation(reservation_id)
    return result


@app.get("/orders", status_code=status.HTTP_200_OK)
async def get_orders(page: int = 1, size: int = 10) -> OrderListResponse:
    """Get paginated orders."""
    result = service.get_orders(page, size)
    orders = [OrderResponse(**order) for order in result["orders"]]
    return OrderListResponse(
        orders=orders,
        page=result["page"],
        size=result["size"],
        total=result["total"],
    )
