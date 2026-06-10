"""FastAPI application for commerce service."""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from . import models
from .repository import Repository, init_db
from .security import verify_api_key
from .service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    InvalidReservationStateError,
    ReservationExpiredError,
)

app = FastAPI(title="Commerce Service API", version="0.1.0")

init_db()
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=models.HealthResponse)
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=dict)
def create_sku(
    request: models.CreateSKURequest,
    api_key: str = Depends(verify_api_key)
):
    """Create a new SKU with initial stock."""
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.post("/stock/adjust", response_model=models.StockAdjustResponse)
def adjust_stock(
    request: models.AdjustStockRequest,
    api_key: str = Depends(verify_api_key)
):
    """Adjust stock for a SKU."""
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.post("/reservations", status_code=201, response_model=models.ReservationResponse)
def create_reservation(
    request: models.ReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    """Create a reservation with idempotency."""
    try:
        result = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key
        )
        return result
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.post("/reservations/{id}/confirm", response_model=models.ConfirmReservationResponse)
def confirm_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    """Confirm a reservation and create an order."""
    try:
        result = service.confirm_reservation(id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reservation expired"
        )


@app.post("/reservations/{id}/cancel", response_model=models.CancelReservationResponse)
def cancel_reservation(
    id: int,
    api_key: str = Depends(verify_api_key)
):
    """Cancel a reservation and restore stock."""
    try:
        result = service.cancel_reservation(id)
        return result
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.get("/orders", response_model=models.OrderListResponse)
def list_orders(page: int = 1, size: int = 10):
    """List orders with pagination."""
    if page < 1 or size < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page and size must be positive"
        )

    result = service.list_orders(page, size)
    return result
