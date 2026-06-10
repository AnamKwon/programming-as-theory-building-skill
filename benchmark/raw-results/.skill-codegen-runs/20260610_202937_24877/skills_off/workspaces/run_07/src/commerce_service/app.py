from fastapi import FastAPI, Depends, HTTPException
from commerce_service.models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderListResponse,
    StockAdjustResponse,
    HealthResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")

_repository: Repository = None
_service: CommerceService = None


def get_repository() -> Repository:
    global _repository
    if _repository is None:
        _repository = Repository()
    return _repository


def get_service() -> CommerceService:
    global _service
    if _service is None:
        _service = CommerceService(get_repository())
    return _service


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    result = service.create_sku(request.sku, request.initial_stock)
    return result


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: AdjustStockRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    return service.adjust_stock(request.sku, request.amount)


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    reservation = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )
    return ReservationResponse(
        id=reservation["id"],
        sku=reservation["sku"],
        quantity=reservation["quantity"],
        status=reservation["status"],
        created_at=reservation["created_at"],
    )


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 10,
    _: str = Depends(verify_api_key),
    service: CommerceService = Depends(get_service),
):
    result = service.get_orders(page, size)
    return OrderListResponse(
        orders=result["orders"],
        page=result["page"],
        size=result["size"],
        total=result["total"],
    )
