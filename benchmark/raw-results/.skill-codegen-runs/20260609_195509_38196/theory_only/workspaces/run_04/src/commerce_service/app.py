from fastapi import FastAPI, Depends, status, Query
from typing import Annotated
from commerce_service.repository import Database
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key
from commerce_service.models import (
    SkuRequest,
    SkuResponse,
    StockAdjustmentRequest,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationRequest,
    OrderResponse,
    PaginatedOrdersResponse,
)

app = FastAPI(title="Commerce Service", version="0.1.0")

_db = None


def get_database() -> Database:
    global _db
    if _db is None:
        _db = Database(":memory:")
    return _db


def get_service() -> CommerceService:
    return CommerceService(get_database())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/skus", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SkuRequest,
    api_key: Annotated[str, Depends(verify_api_key)] = None,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.create_sku(request.name, request.quantity)


@app.post("/skus/{sku_id}/adjust", response_model=SkuResponse)
async def adjust_stock(
    sku_id: int,
    request: StockAdjustmentRequest,
    api_key: Annotated[str, Depends(verify_api_key)] = None,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.adjust_stock(sku_id, request.quantity_delta)


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    request: ReservationRequest,
    api_key: Annotated[str, Depends(verify_api_key)] = None,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.create_reservation(
        request.sku_id, request.quantity, request.idempotency_key
    )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    request: ConfirmReservationRequest,
    api_key: Annotated[str, Depends(verify_api_key)] = None,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    api_key: Annotated[str, Depends(verify_api_key)] = None,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=PaginatedOrdersResponse)
async def get_orders(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
    service: CommerceService = Depends(get_service),
) -> dict:
    return service.get_orders(page, size)
