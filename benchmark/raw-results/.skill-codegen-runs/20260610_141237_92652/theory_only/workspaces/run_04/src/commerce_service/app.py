from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    HealthResponse,
    PaginatedOrdersResponse,
)
from .repository import init_db, get_db
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Inventory & Order API", version="0.1.0")

init_db()


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: CreateSKURequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust", status_code=200)
def adjust_stock(
    request: AdjustStockRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=201)
def create_reservation(
    request: CreateReservationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        reservation, status_code = service.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )
        if status_code == 200:
            return reservation
        return reservation
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", status_code=200)
def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        return service.confirm_reservation(id)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        elif "not in PENDING state" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", status_code=200)
def cancel_reservation(
    id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        return service.cancel_reservation(id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=PaginatedOrdersResponse)
def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    orders, total = service.get_orders(page, size)
    return {
        "page": page,
        "size": size,
        "total": total,
        "orders": orders,
    }
