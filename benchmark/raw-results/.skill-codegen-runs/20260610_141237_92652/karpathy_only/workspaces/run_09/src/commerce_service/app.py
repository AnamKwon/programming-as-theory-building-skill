from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse

from commerce_service.models import (
    CreateSKURequest,
    CreateReservationRequest,
    OrderListResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_key


app = FastAPI(title="Commerce Inventory & Order API")

repository = Repository(":memory:")
service = CommerceService(repository)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201)
async def create_sku(
    request: CreateSKURequest,
    _api_key: str = Depends(verify_api_key),
):
    if not service.create_sku(request.sku, request.initial_stock):
        raise HTTPException(status_code=409, detail="SKU already exists")
    return {
        "sku": request.sku,
        "available_stock": request.initial_stock,
        "reserved_stock": 0,
    }


@app.post("/stock/adjust", status_code=200)
async def adjust_stock(
    request: dict,
    _api_key: str = Depends(verify_api_key),
):
    sku = request.get("sku")
    amount = request.get("amount")

    if sku is None or amount is None:
        raise HTTPException(status_code=400, detail="Missing sku or amount")

    result = service.adjust_stock(sku, amount)
    if result is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    return {
        "sku": result["sku"],
        "available_stock": result["available_stock"],
        "reserved_stock": result["reserved_stock"],
    }


@app.post("/reservations", status_code=201)
async def create_reservation(
    request: CreateReservationRequest,
    _api_key: str = Depends(verify_api_key),
):
    response, status_code = service.create_reservation(
        request.sku, request.quantity, request.idempotency_key
    )

    if response is None:
        if status_code == 400:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=status_code, detail="Failed to create reservation")

    if status_code == 200:
        return JSONResponse(status_code=200, content=response.model_dump(mode="json"))

    return JSONResponse(status_code=201, content=response.model_dump(mode="json"))


@app.post("/reservations/{reservation_id}/confirm", status_code=200)
async def confirm_reservation(
    reservation_id: int,
    _api_key: str = Depends(verify_api_key),
):
    result, status_code = service.confirm_reservation(reservation_id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))
    return result


@app.post("/reservations/{reservation_id}/cancel", status_code=200)
async def cancel_reservation(
    reservation_id: int,
    _api_key: str = Depends(verify_api_key),
):
    result, status_code = service.cancel_reservation(reservation_id)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get("detail"))
    return result


@app.get("/orders", status_code=200)
async def get_orders(page: int = 1, size: int = 10):
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    orders, total, current_page = service.get_orders(page, size)
    return OrderListResponse(
        items=orders,
        page=current_page,
        size=size,
        total=total,
    ).model_dump()
