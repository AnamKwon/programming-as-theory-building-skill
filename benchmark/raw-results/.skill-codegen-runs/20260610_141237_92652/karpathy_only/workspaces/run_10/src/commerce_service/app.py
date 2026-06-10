from fastapi import FastAPI, Depends, HTTPException, status

from .models import (
    SKUCreateRequest, StockAdjustRequest, ReservationCreateRequest,
    ReservationResponse, OrderResponse, OrderListResponse, HealthResponse
)
from .service import Service
from .repository import Repository
from .security import verify_token

repository = Repository("commerce.db")
service = Service(repository)

app = FastAPI()


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(request: SKUCreateRequest, _token: str = Depends(verify_token)):
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust")
async def adjust_stock(request: StockAdjustRequest, _token: str = Depends(verify_token)):
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: ReservationCreateRequest,
    _token: str = Depends(verify_token)
) -> ReservationResponse:
    try:
        return service.create_reservation(request.sku, request.quantity, request.idempotency_key)
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "Insufficient stock":
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    _token: str = Depends(verify_token)
) -> ReservationResponse:
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "Reservation expired":
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    _token: str = Depends(verify_token)
) -> ReservationResponse:
    try:
        return service.cancel_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    orders = service.get_orders(page, size)
    return {
        "orders": [OrderResponse(**order) for order in orders],
        "page": page,
        "size": size
    }
