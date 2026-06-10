"""FastAPI application."""

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjust,
    StockResponse,
)
from .repository import Repository
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

# Initialize repository and service
repository = Repository()
service = CommerceService(repository)


@app.get("/health", status_code=200)
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
def create_sku(
    payload: SKUCreate,
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU."""
    try:
        return service.create_sku(payload.id, payload.name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/stock/{sku_id}/adjust", status_code=200, response_model=StockResponse)
def adjust_stock(
    sku_id: str,
    payload: StockAdjust,
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock for a SKU."""
    try:
        return service.adjust_stock(sku_id, payload.delta)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
def create_reservation(
    payload: ReservationCreate,
    api_key: str = Depends(verify_api_key),
):
    """Create a reservation (idempotent)."""
    try:
        return service.create_reservation(
            payload.sku_id,
            payload.quantity,
            payload.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", status_code=200, response_model=OrderResponse)
def confirm_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Confirm a reservation and create an order."""
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", status_code=200, response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Cancel a pending reservation."""
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", status_code=200, response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """List orders with pagination."""
    result = service.list_orders(page, page_size)
    return OrderListResponse(
        items=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


@app.exception_handler(ValueError)
def value_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )
