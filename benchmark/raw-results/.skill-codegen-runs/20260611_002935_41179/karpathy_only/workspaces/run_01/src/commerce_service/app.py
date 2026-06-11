"""FastAPI application for commerce service."""
from fastapi import FastAPI, HTTPException, Depends, status

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    StockResponse,
    HealthResponse,
    OrderListResponse,
)
from .repository import Database
from .service import CommerceService
from .security import verify_api_key


# Initialize database and service
db = Database(db_path=":memory:")
db.init_schema()
service = CommerceService(db)

# Create FastAPI app
app = FastAPI(title="Commerce Service", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", response_model=dict, status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU already exists",
            )
        raise


@app.post("/stock/adjust", response_model=StockResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
):
    """Adjust stock level for a SKU."""
    result = service.adjust_stock(request.sku, request.amount)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found",
        )
    return result


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
):
    """Create a reservation with idempotency."""
    response, status_code = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key,
    )

    if status_code == "400":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock",
        )

    return response


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    """Confirm a reservation and create an order."""
    response, status_code = service.confirm_reservation(reservation_id)

    if status_code == "404":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )

    if status_code == "400":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation is not in PENDING state",
        )

    if status_code == "400_EXPIRED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation expired",
        )

    return response


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    """Cancel a reservation and restore stock."""
    response, status_code = service.cancel_reservation(reservation_id)

    if status_code == "404":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )

    if status_code == "400":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation is not in PENDING state",
        )

    return response


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    _: str = Depends(verify_api_key),
):
    """Get paginated list of orders."""
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    orders, total = service.get_orders(page, size)

    return {
        "orders": orders,
        "page": page,
        "size": size,
        "total": total,
    }
