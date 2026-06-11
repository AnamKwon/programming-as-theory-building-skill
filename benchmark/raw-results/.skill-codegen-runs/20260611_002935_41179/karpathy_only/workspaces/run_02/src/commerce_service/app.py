from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(title="Commerce Inventory & Order API")
repo = Repository()
service = CommerceService(repo)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest, _api_key: str = Depends(verify_api_key)
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest, _api_key: str = Depends(verify_api_key)
):
    result = service.adjust_stock(request.sku, request.amount)
    return result


@app.post("/reservations")
async def create_reservation(
    request: CreateReservationRequest, _api_key: str = Depends(verify_api_key)
):
    reservation, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    return JSONResponse(status_code=status_code, content=reservation.model_dump())


@app.post("/reservations/{id}/confirm")
async def confirm_reservation(id: int, _api_key: str = Depends(verify_api_key)):
    result = service.confirm_reservation(id)
    return result


@app.post("/reservations/{id}/cancel")
async def cancel_reservation(id: int, _api_key: str = Depends(verify_api_key)):
    result = service.cancel_reservation(id)
    return result


@app.get("/orders")
async def list_orders(page: int = 1, size: int = 10):
    result = service.get_orders(page, size)
    return result
