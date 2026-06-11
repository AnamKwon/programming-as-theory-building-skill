"""FastAPI application for commerce service."""

from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.responses import JSONResponse

from .models import (
    HealthResponse,
    CreateSKURequest,
    CreateSKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    PaginatedOrdersResponse,
    OrderResponse,
)
from .repository import Repository, init_db
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationExpiredError,
    InvalidReservationStatusError,
)
from .security import verify_api_token

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=CreateSKUResponse, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    token: str = Depends(verify_api_token),
):
    """Create a new SKU with initial stock."""
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    token: str = Depends(verify_api_token),
):
    """Adjust stock level for a SKU."""
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    token: str = Depends(verify_api_token),
):
    """Reserve stock for an order."""
    try:
        result = service.reserve_stock(
            request.sku, request.quantity, request.idempotency_key
        )
        return result
    except InsufficientStockError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock",
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    token: str = Depends(verify_api_token),
):
    """Confirm a reservation and create an order."""
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ReservationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation expired",
        )
    except InvalidReservationStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    token: str = Depends(verify_api_token),
):
    """Cancel a reservation and restore stock."""
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except InvalidReservationStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    token: str = Depends(verify_api_token),
):
    """Get paginated list of orders."""
    result = service.get_orders(page, size)
    return result
