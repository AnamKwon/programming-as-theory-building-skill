"""FastAPI application and routes."""

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from commerce_service.models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    OrderResponse,
    PaginatedOrdersResponse,
    ReservationResponse,
    StockResponse,
)
from commerce_service.repository import get_db, init_db
from commerce_service.security import verify_api_token
from commerce_service.service import Service

app = FastAPI(title="Commerce Service")


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize database on startup."""
    init_db()


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
) -> dict:
    """Create a new SKU."""
    service = Service(repository=__import__("commerce_service.repository", fromlist=["Repository"]).Repository(db))
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
) -> StockResponse:
    """Adjust stock for a SKU."""
    from commerce_service.repository import Repository

    service = Service(repository=Repository(db))
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return StockResponse(sku=result["sku"], available_stock=result["available_stock"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
) -> ReservationResponse:
    """Create a reservation."""
    from commerce_service.repository import Repository

    service = Service(repository=Repository(db))
    try:
        return service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
) -> ReservationResponse:
    """Confirm a reservation."""
    from commerce_service.repository import Repository

    service = Service(repository=Repository(db))
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
) -> ReservationResponse:
    """Cancel a reservation."""
    from commerce_service.repository import Repository

    service = Service(repository=Repository(db))
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        if "not PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders", status_code=200)
async def get_orders(
    page: int = 1,
    size: int = 10,
    _: str = Depends(verify_api_token),
    db: Session = Depends(get_db),
) -> PaginatedOrdersResponse:
    """Get paginated list of orders."""
    from commerce_service.repository import Repository

    service = Service(repository=Repository(db))
    result = service.get_orders_paginated(page=page, size=size)
    return PaginatedOrdersResponse(
        page=result["page"],
        size=result["size"],
        total=result["total"],
        orders=result["orders"],
    )
