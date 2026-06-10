from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from commerce_service.models import (
    SKURequest,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from commerce_service.repository import Repository
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_token

app = FastAPI()
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", status_code=201, response_model=SKUResponse)
async def create_sku(
    request: SKURequest,
    token: str = Depends(verify_api_token),
):
    try:
        result = service.create_sku(request.sku, request.initial_stock)
        return SKUResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse)
async def adjust_stock(
    request: StockAdjustRequest,
    token: str = Depends(verify_api_token),
):
    try:
        result = service.adjust_stock(request.sku, request.amount)
        return StockAdjustResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", status_code=201, response_model=ReservationResponse)
async def create_reservation(
    request: ReservationRequest,
    token: str = Depends(verify_api_token),
):
    try:
        reservation, status_code = service.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key,
        )
        if status_code == 200:
            return JSONResponse(
                status_code=200,
                content=ReservationResponse(**reservation).model_dump(mode="json"),
            )
        return ReservationResponse(**reservation)
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/confirm", response_model=ReservationResponse)
async def confirm_reservation(
    id: int,
    token: str = Depends(verify_api_token),
):
    try:
        result = service.confirm_reservation(id)
        return ReservationResponse(**result)
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        if "PENDING" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    id: int,
    token: str = Depends(verify_api_token),
):
    try:
        result = service.cancel_reservation(id)
        return ReservationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(page: int = 1, size: int = 10):
    try:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = service.get_orders(page, size)
        order_responses = [OrderResponse(**order) for order in orders]

        return OrderListResponse(
            items=order_responses,
            page=page,
            size=size,
            total=total,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
