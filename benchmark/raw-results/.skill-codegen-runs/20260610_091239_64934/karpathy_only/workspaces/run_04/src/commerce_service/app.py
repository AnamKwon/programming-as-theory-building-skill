from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
import sqlite3

from .models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    SKUResponse,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from .repository import Repository
from .service import Service
from .security import api_key_header, verify_api_key

app = FastAPI(title="Commerce Service", version="0.1.0")
repo = Repository()
service = Service(repo)


@app.on_event("startup")
async def startup():
    repo.init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201, dependencies=[Depends(verify_api_key)])
async def create_sku(req: CreateSKURequest, api_key: str = Depends(api_key_header)):
    try:
        return service.create_sku(req)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU code '{req.sku_code}' already exists",
        )


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
async def adjust_stock(
    sku_id: int,
    req: AdjustStockRequest,
    api_key: str = Depends(api_key_header),
):
    return service.adjust_stock(sku_id, req.quantity)


@app.post("/orders", response_model=OrderResponse, status_code=201, dependencies=[Depends(verify_api_key)])
async def create_order(api_key: str = Depends(api_key_header)):
    return service.create_order()


@app.post(
    "/orders/{order_id}/reservations",
    response_model=ReservationResponse,
    status_code=201,
    dependencies=[Depends(verify_api_key)],
)
async def create_reservation(
    order_id: int,
    req: CreateReservationRequest,
    api_key: str = Depends(api_key_header),
):
    return service.create_reservation(order_id, req)


@app.post(
    "/orders/{order_id}/reservations/{reservation_id}/confirm",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def confirm_reservation(
    order_id: int,
    reservation_id: int,
    api_key: str = Depends(api_key_header),
):
    return service.confirm_reservation(order_id, reservation_id)


@app.post(
    "/orders/{order_id}/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    dependencies=[Depends(verify_api_key)],
)
async def cancel_reservation(
    order_id: int,
    reservation_id: int,
    api_key: str = Depends(api_key_header),
):
    return service.cancel_reservation(order_id, reservation_id)


@app.get("/orders", response_model=OrderListResponse)
async def list_orders(offset: int = 0, limit: int = 20):
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters",
        )
    orders, total = repo.list_orders(offset, limit)
    return OrderListResponse(
        total=total,
        limit=limit,
        offset=offset,
        orders=orders,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int):
    return service.get_order(order_id)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
