from fastapi import FastAPI, Depends, HTTPException, status
from commerce_service.models import (
    HealthResponse, CreateSKURequest, AdjustStockRequest,
    CreateReservationRequest, ReservationResponse, OrderResponse,
    OrderListResponse, StockResponse, ErrorResponse
)
from commerce_service.security import verify_api_key
from commerce_service.repository import Repository
from commerce_service.service import CommerceService

app = FastAPI(title="Commerce Service")

_repo = Repository()
_service = CommerceService(_repo)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201, dependencies=[Depends(verify_api_key)])
async def create_sku(request: CreateSKURequest):
    success = _service.create_sku(request.sku, request.initial_stock)
    if not success:
        raise HTTPException(status_code=400, detail="SKU already exists")
    return {"sku": request.sku, "initial_stock": request.initial_stock}


@app.post("/stock/adjust", response_model=StockResponse, dependencies=[Depends(verify_api_key)])
async def adjust_stock(request: AdjustStockRequest):
    available_stock = _service.adjust_stock(request.sku, request.amount)
    if available_stock is None:
        raise HTTPException(status_code=400, detail="SKU not found")
    return {"sku": request.sku, "available_stock": available_stock}


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(request: CreateReservationRequest):
    result, status_code = _service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if status_code == "sku_not_found":
        raise HTTPException(status_code=400, detail="SKU not found")
    elif status_code == "insufficient_stock":
        raise HTTPException(status_code=400, detail="Insufficient stock")
    elif status_code == "creation_failed":
        raise HTTPException(status_code=500, detail="Failed to create reservation")
    elif status_code in ("created", "idempotent"):
        return ReservationResponse(
            id=result['id'],
            sku=result['sku'],
            quantity=result['quantity'],
            status=result['status'],
            created_at=result['created_at']
        )

    raise HTTPException(status_code=500, detail="Unexpected error")


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(reservation_id: int):
    result, status_code = _service.confirm_reservation(reservation_id)

    if status_code == "not_found":
        raise HTTPException(status_code=400, detail="Reservation not found")
    elif status_code == "invalid_state":
        raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
    elif status_code == "expired":
        raise HTTPException(status_code=400, detail="Reservation expired")
    elif status_code == "order_creation_failed":
        raise HTTPException(status_code=500, detail="Failed to create order")
    elif status_code == "confirmed":
        return OrderResponse(
            id=result['id'],
            reservation_id=result['reservation_id'],
            created_at=result['created_at']
        )

    raise HTTPException(status_code=500, detail="Unexpected error")


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(reservation_id: int):
    result, status_code = _service.cancel_reservation(reservation_id)

    if status_code == "not_found":
        raise HTTPException(status_code=400, detail="Reservation not found")
    elif status_code == "invalid_state":
        raise HTTPException(status_code=400, detail="Reservation is not in PENDING state")
    elif status_code == "cancelled":
        return ReservationResponse(
            id=result['id'],
            sku=result['sku'],
            quantity=result['quantity'],
            status=result['status'],
            created_at=result['created_at']
        )

    raise HTTPException(status_code=500, detail="Unexpected error")


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    orders, total = _service.get_orders(page, size)

    return OrderListResponse(
        items=[
            OrderResponse(
                id=order['id'],
                reservation_id=order['reservation_id'],
                created_at=order['created_at']
            )
            for order in orders
        ],
        page=page,
        size=size,
        total=total
    )
