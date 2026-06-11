"""FastAPI application and routes."""
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .repository import init_db, get_db, Repository
from .security import verify_api_key
from .service import CommerceService
from .models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderListResponse,
)

app = FastAPI(title="Commerce Service")

init_db()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
def create_sku(
    request: SKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Create a new SKU with initial stock."""
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.create_sku(request.sku, request.initial_stock)
        return SKUResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
def adjust_stock(
    request: StockAdjustRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Adjust stock levels for a SKU."""
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.adjust_stock(request.sku, request.amount)
        return StockAdjustResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
def create_reservation(
    request: ReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Create a reservation (idempotent by idempotency_key)."""
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key,
        )
        return result
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Confirm a reservation and create an order."""
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Cancel a reservation and restore stock."""
    try:
        repository = Repository(db)
        service = CommerceService(repository)
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        if "not in PENDING" in str(e):
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    """Get paginated list of orders."""
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    repository = Repository(db)
    service = CommerceService(repository)
    result = service.get_orders_paginated(page, size)
    return OrderListResponse(**result)
