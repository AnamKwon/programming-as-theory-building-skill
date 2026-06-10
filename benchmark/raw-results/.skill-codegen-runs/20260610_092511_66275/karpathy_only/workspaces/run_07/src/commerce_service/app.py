from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse

from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    ReservationCreate,
    ReservationResponse,
    ReservationConfirm,
    OrderResponse,
    OrderList,
)
from .repository import Repository
from .service import CommerceService, InsufficientStock, NotFound, ReservationExpired
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = CommerceService(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    payload: SKUCreate,
    _: str = Depends(verify_api_key),
):
    sku = service.create_sku(payload.sku_code, payload.quantity)
    return SKUResponse(**sku)


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: int,
    payload: StockAdjustment,
    _: str = Depends(verify_api_key),
):
    try:
        sku = service.adjust_stock(sku_id, payload.delta)
        return SKUResponse(**sku)
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate,
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.create_reservation(
            payload.sku_id,
            payload.quantity,
            payload.idempotency_key,
        )
        return ReservationResponse(**reservation)
    except InsufficientStock as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpired as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: int,
    payload: ReservationConfirm,
    _: str = Depends(verify_api_key),
):
    try:
        order = service.confirm_reservation(reservation_id)
        return OrderResponse(**order)
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReservationExpired as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    _: str = Depends(verify_api_key),
):
    try:
        reservation = service.cancel_reservation(reservation_id)
        return ReservationResponse(**reservation)
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderList)
async def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    result = service.list_orders(offset, limit)
    orders = [OrderResponse(**order) for order in result["items"]]
    return OrderList(items=orders, total=result["total"], offset=offset, limit=limit)


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int):
    try:
        order = service.get_order(order_id)
        return OrderResponse(**order)
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
