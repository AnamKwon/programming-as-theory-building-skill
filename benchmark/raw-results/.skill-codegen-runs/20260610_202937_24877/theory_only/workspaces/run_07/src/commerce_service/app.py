from fastapi import FastAPI, Depends, status
from .models import (
    CreateSKURequest,
    StockAdjustmentRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    OrderListResponse,
    StockAdjustmentResponse,
    HealthResponse
)
from .repository import Database
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Service API")

db = Database(":memory:")
service = CommerceService(db)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=StockAdjustmentResponse)
async def adjust_stock(
    request: StockAdjustmentRequest,
    api_key: str = Depends(verify_api_key)
):
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    reservation, status_code = service.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key
    )
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=ConfirmReservationResponse)
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key)
):
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key)
):
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    return service.get_orders(page, size)
