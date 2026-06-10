from typing import Annotated

from fastapi import FastAPI, Depends, status

from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    ReservationConfirm,
    OrderResponse,
    OrderListResponse,
)
from .repository import Database
from .security import verify_api_key
from .service import CommerceService

app = FastAPI(title="Commerce Service", version="0.1.0")

db = Database()
service = CommerceService(db)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: SKUCreate,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict:
    return service.create_sku(payload.sku_id, payload.name, payload.initial_stock)


@app.post(
    "/skus/{sku_id}/adjust-stock",
    response_model=SKUResponse,
    status_code=status.HTTP_200_OK,
)
async def adjust_stock(
    sku_id: str,
    payload: StockAdjustment,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict:
    return service.adjust_stock(sku_id, payload.quantity_delta)


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    payload: ReservationCreate,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict:
    return service.create_reservation(
        payload.sku_id, payload.quantity, payload.idempotency_key
    )


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_reservation(
    reservation_id: str,
    payload: ReservationConfirm,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict:
    return service.confirm_reservation(reservation_id)


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_reservation(
    reservation_id: str,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict:
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(limit: int = 20, offset: int = 0) -> dict:
    orders, total = service.list_orders(limit, offset)
    return {"orders": orders, "total": total, "limit": limit, "offset": offset}


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> dict:
    return service.get_order(order_id)
