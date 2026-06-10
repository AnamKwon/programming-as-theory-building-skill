from typing import Annotated

from fastapi import Depends, FastAPI, status

from .models import (
    AdjustStockRequest,
    CreateReservationRequest,
    CreateSKURequest,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import Database
from .security import get_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

db = Database("commerce.db")
service = CommerceService(db)

APIKeyDep = Annotated[str, Depends(get_api_key)]


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    req: CreateSKURequest,
    _: APIKeyDep,
):
    sku_dict = service.create_sku(req.sku, req.name, req.initial_stock)
    return SKUResponse(**sku_dict)


@app.put("/skus/{sku_id}/stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    req: AdjustStockRequest,
    _: APIKeyDep,
):
    sku_dict = service.adjust_stock(sku_id, req.adjustment)
    return SKUResponse(**sku_dict)


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    req: CreateReservationRequest,
    _: APIKeyDep,
):
    res_dict = service.create_reservation(
        req.order_id,
        req.sku_id,
        req.quantity,
        req.idempotency_key,
    )
    return ReservationResponse(**res_dict)


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    _: APIKeyDep,
):
    res_dict = service.confirm_reservation(reservation_id)
    return ReservationResponse(**res_dict)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: APIKeyDep,
):
    res_dict = service.cancel_reservation(reservation_id)
    return ReservationResponse(**res_dict)


@app.get("/orders")
async def list_orders(
    limit: int = 50,
    offset: int = 0,
    _: APIKeyDep = None,
):
    result = service.get_orders(limit, offset)
    return {
        "items": [OrderResponse(**order) for order in result["items"]],
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
    }
