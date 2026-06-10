from fastapi import FastAPI, Depends, status
from .repository import Repository
from .service import CommerceService
from .security import validate_api_token
from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
)


app = FastAPI(title="Commerce Service API")
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", status_code=status.HTTP_201_CREATED)
def create_sku(
    request: CreateSKURequest, token: str = Depends(validate_api_token)
):
    return service.create_sku(request.sku, request.initial_stock)


@app.post("/stock/adjust")
def adjust_stock(
    request: AdjustStockRequest, token: str = Depends(validate_api_token)
):
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", status_code=status.HTTP_201_CREATED)
def create_reservation(
    request: CreateReservationRequest, token: str = Depends(validate_api_token)
) -> ReservationResponse:
    return service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )


@app.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int, token: str = Depends(validate_api_token)
):
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int, token: str = Depends(validate_api_token)
):
    return service.cancel_reservation(reservation_id)


@app.get("/orders")
def get_orders(
    page: int = 1, size: int = 10, token: str = Depends(validate_api_token)
) -> OrderListResponse:
    return service.get_orders(page, size)
