from fastapi import FastAPI, Depends, Query
from typing import Annotated
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key
from . import models

app = FastAPI(title="Commerce Service", version="0.1.0")

# Shared dependencies
_repo = Repository()
_service = CommerceService(_repo)


async def get_service() -> CommerceService:
    return _service


@app.get("/health", response_model=models.HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=models.SKUResponse, dependencies=[Depends(verify_api_key)])
async def create_sku(
    req: models.SKUCreate, service: CommerceService = Depends(get_service)
):
    sku = service.create_sku(req.name)
    return models.SKUResponse(
        id=sku["id"],
        name=sku["name"],
        created_at=sku["created_at"],
    )


@app.post("/stock/{sku_id}/adjust", response_model=models.StockResponse, dependencies=[Depends(verify_api_key)])
async def adjust_stock(
    sku_id: int,
    req: models.StockAdjustRequest,
    service: CommerceService = Depends(get_service),
):
    stock = service.adjust_stock(sku_id, req.delta)
    return models.StockResponse(
        sku_id=stock["sku_id"],
        quantity=stock["quantity"],
        updated_at=stock["updated_at"],
    )


@app.post("/reservations", response_model=models.ReservationResponse, dependencies=[Depends(verify_api_key)])
async def create_reservation(
    req: models.ReservationCreateRequest,
    service: CommerceService = Depends(get_service),
):
    reservation = service.create_reservation(
        req.sku_id, req.quantity, req.idempotency_key, req.ttl_seconds
    )
    return models.ReservationResponse(
        id=reservation["id"],
        sku_id=reservation["sku_id"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        idempotency_key=reservation["idempotency_key"],
        created_at=reservation["created_at"],
        expires_at=reservation["expires_at"],
    )


@app.post("/reservations/{reservation_id}/confirm", response_model=models.ReservationResponse, dependencies=[Depends(verify_api_key)])
async def confirm_reservation(
    reservation_id: int, service: CommerceService = Depends(get_service)
):
    reservation = service.confirm_reservation(reservation_id)
    return models.ReservationResponse(
        id=reservation["id"],
        sku_id=reservation["sku_id"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        idempotency_key=reservation["idempotency_key"],
        created_at=reservation["created_at"],
        expires_at=reservation["expires_at"],
    )


@app.post("/reservations/{reservation_id}/cancel", response_model=models.ReservationResponse, dependencies=[Depends(verify_api_key)])
async def cancel_reservation(
    reservation_id: int, service: CommerceService = Depends(get_service)
):
    reservation = service.cancel_reservation(reservation_id)
    return models.ReservationResponse(
        id=reservation["id"],
        sku_id=reservation["sku_id"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        idempotency_key=reservation["idempotency_key"],
        created_at=reservation["created_at"],
        expires_at=reservation["expires_at"],
    )


@app.get("/orders", response_model=models.OrderListResponse)
async def list_orders(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[int, Query(ge=0)] = 0,
    service: CommerceService = Depends(get_service),
):
    orders, next_cursor = service.list_orders(limit, cursor)
    return models.OrderListResponse(
        items=[
            models.OrderResponse(
                id=o["id"],
                reservation_id=o["reservation_id"],
                sku_id=o["sku_id"],
                quantity=o["quantity"],
                status=o["status"],
                created_at=o["created_at"],
            )
            for o in orders
        ],
        next_cursor=next_cursor,
    )
