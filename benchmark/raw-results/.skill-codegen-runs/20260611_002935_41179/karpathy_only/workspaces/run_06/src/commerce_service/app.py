from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
)
from .repository import Repository
from .service import Service
from .security import verify_api_key

app = FastAPI(title="Commerce Service")
repo = Repository()
service = Service(repo)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(verify_api_key),
) -> dict:
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(verify_api_key),
) -> ReservationResponse:
    return service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
) -> ConfirmReservationResponse:
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(verify_api_key),
) -> dict:
    return service.cancel_reservation(reservation_id)


@app.get("/orders")
async def list_orders(page: int = 1, size: int = 10) -> dict:
    return service.list_orders(page, size)
