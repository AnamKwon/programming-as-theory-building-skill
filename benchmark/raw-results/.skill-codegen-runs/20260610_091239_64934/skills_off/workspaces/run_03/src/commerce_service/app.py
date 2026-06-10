from fastapi import FastAPI, Depends, Query
from fastapi.responses import JSONResponse

from .models import (
    SKUCreate,
    SKUResponse,
    ReservationCreate,
    ReservationResponse,
    StockAdjustment,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
    ErrorResponse,
)
from .repository import Database
from .service import CommerceService
from .security import verify_api_key

app = FastAPI(
    title="Commerce Service",
    description="Inventory reservation and order orchestration API",
    version="0.1.0",
)

db = Database("commerce.db")
service = CommerceService(db)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201)
def create_sku(sku: SKUCreate, api_key: str = Depends(verify_api_key)):
    try:
        result = service.create_sku(sku.code, sku.name, sku.initial_stock)
        return result
    except Exception as e:
        if "already exists" in str(e):
            return JSONResponse(
                status_code=409, content={"detail": str(e)}
            )
        raise


@app.post("/stock/{sku_id}/adjust", response_model=SKUResponse)
def adjust_stock(
    sku_id: int, adjustment: StockAdjustment, api_key: str = Depends(verify_api_key)
):
    return service.adjust_stock(sku_id, adjustment.quantity)


@app.post("/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(
    reservation: ReservationCreate, api_key: str = Depends(verify_api_key)
):
    return service.create_reservation(
        reservation.sku_id, reservation.quantity, reservation.idempotency_key
    )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: int, api_key: str = Depends(verify_api_key)
):
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: int, api_key: str = Depends(verify_api_key)
):
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
def list_orders(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return service.list_orders(offset, limit)


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int):
    return service.get_order(order_id)


@app.exception_handler(ValueError)
def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )
