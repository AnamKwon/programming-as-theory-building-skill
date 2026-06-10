from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    PaginatedOrdersResponse,
    HealthResponse,
)
from .repository import Repository
from .service import CommerceService
from .security import validate_api_key

app = FastAPI(title="Commerce Inventory & Order API")

_default_repo = Repository(db_path=":memory:")
_default_service = CommerceService(_default_repo)


def get_service() -> CommerceService:
    return _default_service


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    api_key: str = Depends(validate_api_key),
    svc: CommerceService = Depends(get_service)
):
    try:
        sku_id = svc.create_sku(request.sku, request.initial_stock)
        return {
            "id": sku_id,
            "sku": request.sku,
            "initial_stock": request.initial_stock
        }
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="SKU already exists")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stock/adjust")
async def adjust_stock(
    request: AdjustStockRequest,
    api_key: str = Depends(validate_api_key),
    svc: CommerceService = Depends(get_service)
):
    updated_stock = svc.adjust_stock(request.sku, request.amount)
    if updated_stock is None:
        raise HTTPException(status_code=400, detail="SKU not found")
    return {
        "sku": request.sku,
        "amount": request.amount,
        "updated_stock": updated_stock
    }


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    api_key: str = Depends(validate_api_key),
    svc: CommerceService = Depends(get_service)
):
    result, status_code = svc.create_reservation(
        request.sku,
        request.quantity,
        request.idempotency_key
    )

    if status_code != 201:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))

    return result


@app.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: int,
    api_key: str = Depends(validate_api_key),
    svc: CommerceService = Depends(get_service)
):
    result, status_code = svc.confirm_reservation(reservation_id)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))

    return result


@app.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    api_key: str = Depends(validate_api_key),
    svc: CommerceService = Depends(get_service)
):
    result, status_code = svc.cancel_reservation(reservation_id)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))

    return result


@app.get("/orders")
async def get_orders(page: int = 1, size: int = 10, svc: CommerceService = Depends(get_service)):
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if size < 1:
        raise HTTPException(status_code=400, detail="Size must be >= 1")

    result = svc.get_orders(page, size)
    return result
