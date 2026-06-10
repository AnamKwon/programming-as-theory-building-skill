from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .repository import init_db, get_db
from .security import verify_api_key
from .service import CommerceService
from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationCreate,
    ReservationResponse,
    OrderListResponse,
)

app = FastAPI(title="Commerce Inventory & Order API", version="0.1.0")

init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(
    sku_create: SKUCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    db_sku = service.create_sku(sku_create)
    return SKUResponse(
        id=db_sku.id,
        sku=db_sku.sku,
        available_stock=db_sku.available_stock,
    )


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    db_sku = service.adjust_stock(request.sku, request.amount)
    if not db_sku:
        raise HTTPException(status_code=404, detail="SKU not found")
    return StockAdjustResponse(sku=db_sku.sku, available_stock=db_sku.available_stock)


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    reservation_create: ReservationCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation = service.create_reservation(reservation_create)
    if not reservation:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    return ReservationResponse(
        id=reservation.id,
        sku=reservation.sku,
        quantity=reservation.quantity,
        status=reservation.status,
        idempotency_key=reservation.idempotency_key,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
    )


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation, status = service.confirm_reservation(id)

    if status == "not_found":
        raise HTTPException(status_code=404, detail="Reservation not found")
    elif status == "invalid_state":
        raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
    elif status == "expired":
        raise HTTPException(status_code=400, detail="Reservation expired")

    return ReservationResponse(
        id=reservation.id,
        sku=reservation.sku,
        quantity=reservation.quantity,
        status=reservation.status,
        idempotency_key=reservation.idempotency_key,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
    )


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    reservation, status = service.cancel_reservation(id)

    if status == "not_found":
        raise HTTPException(status_code=404, detail="Reservation not found")
    elif status == "invalid_state":
        raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")

    return ReservationResponse(
        id=reservation.id,
        sku=reservation.sku,
        quantity=reservation.quantity,
        status=reservation.status,
        idempotency_key=reservation.idempotency_key,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
    )


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    return service.get_orders(page, size)
