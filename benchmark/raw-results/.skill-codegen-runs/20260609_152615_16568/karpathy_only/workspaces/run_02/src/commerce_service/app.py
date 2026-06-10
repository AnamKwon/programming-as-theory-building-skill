from fastapi import FastAPI, Depends, HTTPException, Query
from datetime import datetime
from .repository import init_db, OrderRepository
from .models import (
    HealthResponse,
    SKURequest,
    SKUResponse,
    StockAdjustmentRequest,
    ReservationRequest,
    ReservationResponse,
    ConfirmReservationRequest,
    CancelReservationRequest,
    OrderResponse,
    OrderListResponse,
    ReservationStatus,
    OrderStatus,
)
from .service import SKUService, ReservationService
from .security import verify_api_key

init_db()

app = FastAPI(title="Commerce Service", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def create_sku(request: SKURequest):
    return SKUService.create_sku(request.sku_id, request.stock)


@app.patch("/skus/{sku_id}/stock", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def adjust_stock(sku_id: str, request: StockAdjustmentRequest):
    return SKUService.adjust_stock(sku_id, request.delta)


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
async def create_reservation(request: ReservationRequest):
    result = ReservationService.create_reservation(
        request.sku_id, request.quantity, request.idempotency_key
    )
    return ReservationResponse(
        reservation_id=result["reservation_id"],
        sku_id=result["sku_id"],
        quantity=result["quantity"],
        status=ReservationStatus(result["status"]),
        expires_at=datetime.fromisoformat(result["expires_at"]),
    )


@app.post(
    "/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(reservation_id: str, request: ConfirmReservationRequest):
    result = ReservationService.confirm_reservation(reservation_id)
    return ReservationResponse(
        reservation_id=result["reservation_id"],
        sku_id=result["sku_id"],
        quantity=result["quantity"],
        status=ReservationStatus(result["status"]),
        expires_at=datetime.fromisoformat(result["expires_at"]),
    )


@app.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def cancel_reservation(reservation_id: str, request: CancelReservationRequest):
    result = ReservationService.cancel_reservation(reservation_id)
    return ReservationResponse(
        reservation_id=result["reservation_id"],
        sku_id=result["sku_id"],
        quantity=result["quantity"],
        status=ReservationStatus(result["status"]),
        expires_at=datetime.fromisoformat(result["expires_at"]),
    )


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
    orders, total = OrderRepository.list_all(limit, offset)
    items = [
        OrderResponse(
            order_id=order["order_id"],
            sku_id=order["sku_id"],
            quantity=order["quantity"],
            status=OrderStatus(order["status"]),
            created_at=datetime.fromisoformat(order["created_at"]),
        )
        for order in orders
    ]
    return OrderListResponse(items=items, total=total, limit=limit, offset=offset)
