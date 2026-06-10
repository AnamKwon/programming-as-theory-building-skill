from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse

from .repository import Database
from .service import CommerceService
from .security import validate_api_token
from .models import (
    SKUCreate,
    StockAdjust,
    ReservationCreate,
    ReservationResponse,
    OrderList,
)

app = FastAPI(title="Commerce Service")

db = Database()
service = CommerceService(db)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    payload: SKUCreate,
    token: str = Depends(validate_api_token),
):
    result = service.create_sku(payload.sku, payload.initial_stock)
    return {
        "id": result["id"],
        "sku": result["sku"],
        "available_stock": result["available_stock"],
    }


@app.post("/stock/adjust")
async def adjust_stock(
    payload: StockAdjust,
    token: str = Depends(validate_api_token),
):
    result = service.adjust_stock(payload.sku, payload.amount)
    return {
        "sku": result["sku"],
        "available_stock": result["available_stock"],
    }


@app.post("/reservations", status_code=201)
async def create_reservation(
    payload: ReservationCreate,
    token: str = Depends(validate_api_token),
):
    reservation = service.create_reservation(
        payload.sku,
        payload.quantity,
        payload.idempotency_key,
    )
    return reservation.model_dump()


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(
    id: int,
    token: str = Depends(validate_api_token),
):
    reservation = service.confirm_reservation(id)
    return reservation.model_dump()


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(
    id: int,
    token: str = Depends(validate_api_token),
):
    reservation = service.cancel_reservation(id)
    return reservation.model_dump()


@app.get("/orders")
async def list_orders(
    page: int = 1,
    size: int = 10,
    token: str = Depends(validate_api_token),
):
    result = service.get_orders(page, size)
    return OrderList(
        items=result["items"],
        page=result["page"],
        size=result["size"],
        total=result["total"],
    ).model_dump()


@app.on_event("shutdown")
async def shutdown_event():
    db.close()
