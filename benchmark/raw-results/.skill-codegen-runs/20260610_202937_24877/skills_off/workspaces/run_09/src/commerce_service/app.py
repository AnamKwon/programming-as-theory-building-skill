from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
)
from .repository import init_db, get_db
from .security import verify_api_token
from .service import CommerceService

app = FastAPI(title="Commerce Service API")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
def create_sku(
    request: CreateSKURequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    sku = service.create_sku(request.sku, request.initial_stock)
    return {
        "id": sku.id,
        "sku": sku.sku,
        "available_stock": sku.available_stock,
    }


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    updated = service.adjust_stock(request.sku, request.amount)
    if not updated:
        raise HTTPException(status_code=404, detail="SKU not found")
    return {
        "sku": updated.sku,
        "available_stock": updated.available_stock,
    }


@app.post("/reservations", status_code=201)
def create_reservation(
    request: CreateReservationRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    response, status_code = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key,
    )
    if status_code != 201:
        raise HTTPException(status_code=status_code, detail=response.get("detail"))
    return response


@app.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    response, status_code = service.confirm_reservation(reservation_id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get("detail"))
    return response


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(verify_api_token),
):
    service = CommerceService(db)
    response, status_code = service.cancel_reservation(reservation_id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get("detail"))
    return response


@app.get("/orders")
def get_orders(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    service = CommerceService(db)
    response, status_code = service.get_orders(page, size)
    return response
