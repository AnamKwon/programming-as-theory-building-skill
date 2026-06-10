import uvicorn
from fastapi import FastAPI, Depends, Query

from .models import (
    CreateSKURequest,
    SKUResponse,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
)
from .repository import Repository, SKUModel, ReservationModel, OrderModel
from .service import CommerceService
from .security import verify_api_key


app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)

_repository = Repository()
_service = CommerceService(_repository)


def get_service() -> CommerceService:
    return _service


def _sku_to_response(sku: SKUModel) -> SKUResponse:
    available = sku.current_stock - sku.reserved_stock
    return SKUResponse(
        sku_id=sku.sku_id,
        name=sku.name,
        current_stock=sku.current_stock,
        reserved_stock=sku.reserved_stock,
        available_stock=available,
    )


def _reservation_to_response(res: ReservationModel) -> ReservationResponse:
    return ReservationResponse(
        reservation_id=res.reservation_id,
        sku_id=res.sku_id,
        quantity=res.quantity,
        status=res.status,
        created_at=res.created_at,
        expires_at=res.expires_at,
    )


def _order_to_response(order: OrderModel) -> OrderResponse:
    reservations = [_reservation_to_response(r) for r in order.reservations]
    return OrderResponse(
        order_id=order.order_id,
        status=order.status,
        created_at=order.created_at,
        reservations=reservations,
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse()


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    request: CreateSKURequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    sku = service.create_sku(request.sku_id, request.name, request.initial_stock)
    return _sku_to_response(sku)


@app.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(
    sku_id: str,
    service: CommerceService = Depends(get_service),
):
    sku = service.get_sku(sku_id)
    return _sku_to_response(sku)


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    request: AdjustStockRequest,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    sku = service.adjust_stock(sku_id, request.delta)
    return _sku_to_response(sku)


@app.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    service: CommerceService = Depends(get_service),
):
    reservation = service.create_reservation(
        request.sku_id,
        request.quantity,
        request.idempotency_key,
    )
    return _reservation_to_response(reservation)


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    reservation = service.confirm_reservation(reservation_id)
    return _reservation_to_response(reservation)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    reservation = service.cancel_reservation(reservation_id)
    return _reservation_to_response(reservation)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    orders, total = service.list_orders(skip, limit)
    items = [_order_to_response(order) for order in orders]
    return OrderListResponse(items=items, total=total, skip=skip, limit=limit)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    service: CommerceService = Depends(get_service),
):
    order = service.get_order(order_id)
    return _order_to_response(order)


def run():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
