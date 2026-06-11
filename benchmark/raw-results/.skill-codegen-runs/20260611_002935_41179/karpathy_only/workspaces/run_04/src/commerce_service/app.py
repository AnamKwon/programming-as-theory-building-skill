from fastapi import FastAPI, Depends, status
from commerce_service.models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    HealthResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API")
repository = Repository()
service = CommerceService(repository)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key)
):
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key)
):
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key)
):
    return service.create_reservation(request.sku, request.quantity, request.idempotency_key)


@app.post("/reservations/{reservation_id}/confirm")
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


@app.get("/orders")
async def get_orders(page: int = 1, size: int = 10):
    return service.get_orders(page, size)
