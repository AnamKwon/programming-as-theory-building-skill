from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from commerce_service.repository import init_db, get_db
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key
from commerce_service.models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    OrderListResponse,
)

app = FastAPI(title="Commerce Service", version="0.1.0")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
def create_sku(
    payload: SKUCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.create_sku(payload.sku_name, payload.initial_stock)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/stock/adjust", response_model=SKUResponse)
def adjust_stock(
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.adjust_stock(payload.sku_id, payload.quantity_delta)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    payload: ReservationCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.create_reservation(
            payload.sku_id, payload.quantity, payload.idempotency_key
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.confirm_reservation(reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    service = CommerceService(db)
    try:
        result = service.cancel_reservation(reservation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be 1-100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be >= 0")

    service = CommerceService(db)
    result = service.get_orders(limit, offset)
    return result
