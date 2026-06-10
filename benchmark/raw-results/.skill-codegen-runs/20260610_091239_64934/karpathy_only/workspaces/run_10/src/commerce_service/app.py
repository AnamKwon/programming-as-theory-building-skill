from fastapi import FastAPI, Depends, Query
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key
from .models import (
    SKURequest, StockAdjustment, ReservationRequest,
    ReservationResponse, OrderResponse, OrdersPage
)

app = FastAPI(title="Commerce Service")

repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.post("/skus")
async def create_sku(
    request: SKURequest,
    _: str = Depends(verify_api_key)
) -> dict:
    return service.create_sku(request.sku, request.name)


@app.post("/stock")
async def adjust_stock(
    request: StockAdjustment,
    _: str = Depends(verify_api_key)
) -> dict:
    return service.adjust_stock(request.sku, request.quantity)


@app.post("/reservations")
async def create_reservation(
    request: ReservationRequest,
    _: str = Depends(verify_api_key)
) -> ReservationResponse:
    return service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key,
        request.ttl_seconds
    )


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key)
) -> OrderResponse:
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    _: str = Depends(verify_api_key)
) -> ReservationResponse:
    return service.cancel_reservation(reservation_id)


@app.get("/orders/{order_id}")
async def get_order(order_id: str) -> OrderResponse:
    return service.get_order(order_id)


@app.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
) -> OrdersPage:
    result = service.list_orders(page, page_size)
    return OrdersPage(**result)
