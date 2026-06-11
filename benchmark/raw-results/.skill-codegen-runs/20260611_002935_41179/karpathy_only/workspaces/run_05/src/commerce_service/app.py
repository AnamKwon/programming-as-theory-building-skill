"""FastAPI application and routes."""

from fastapi import Depends, FastAPI, HTTPException, Query, status

from .models import (
    AdjustStockRequest,
    CancelReservationResponse,
    ConfirmReservationResponse,
    CreateReservationRequest,
    CreateSKURequest,
    PaginatedOrdersResponse,
    ReservationResponse,
    StockAdjustResponse,
)
from .repository import Repository, init_db
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service")
repository = Repository()
service = CommerceService(repository)


@app.on_event("startup")
def startup():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
) -> StockAdjustResponse:
    """Adjust stock level for a SKU."""
    try:
        return service.adjust_stock(request.sku, request.amount)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", status_code=201)
def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
) -> ReservationResponse:
    """Create a reservation."""
    try:
        return service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
    except ValueError as e:
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )


@app.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
) -> ConfirmReservationResponse:
    """Confirm a reservation."""
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        error_msg = str(e)
        if "Reservation expired" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )
        if "not in PENDING state" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING state",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
) -> CancelReservationResponse:
    """Cancel a reservation."""
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        error_msg = str(e)
        if "not in PENDING state" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING state",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )


@app.get("/orders")
def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    _: str = Depends(verify_api_key),
) -> PaginatedOrdersResponse:
    """Get paginated orders."""
    return service.get_orders(page, size)
