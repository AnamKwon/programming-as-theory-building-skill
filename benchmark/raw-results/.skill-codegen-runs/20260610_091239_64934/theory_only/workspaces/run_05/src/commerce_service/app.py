from fastapi import FastAPI, HTTPException, Depends, status, Query

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
from .service import Service
from .security import verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository("commerce.db")


def get_service() -> Service:
    return Service(repo)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse)
async def create_sku(
    req: SKUCreate,
    service: Service = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        return service.create_sku(req.sku_id, req.quantity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/skus/{sku_id}/adjust-stock", response_model=SKUResponse)
async def adjust_stock(
    sku_id: str,
    req: StockAdjustment,
    service: Service = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        return service.adjust_stock(sku_id, req.delta)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    req: ReservationCreate,
    service: Service = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        return service.create_reservation(req.sku_id, req.quantity, req.idempotency_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
async def confirm_reservation(
    reservation_id: str,
    _: ReservationConfirm,
    service: Service = Depends(get_service),
    __: str = Depends(verify_api_key),
):
    try:
        return service.confirm_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reservation(
    reservation_id: str,
    service: Service = Depends(get_service),
    _: str = Depends(verify_api_key),
):
    try:
        service.cancel_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/orders", response_model=OrderList)
async def list_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: Service = Depends(get_service),
):
    orders, total = service.get_orders(limit, offset)
    return OrderList(orders=orders, total=total, limit=limit, offset=offset)
