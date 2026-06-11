"""FastAPI application definition."""

from fastapi import FastAPI, Depends, status
from src.commerce_service.models import (
    SKUCreate,
    SKUResponse,
    StockAdjustment,
    StockAdjustmentResponse,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
    HealthResponse,
)
from src.commerce_service.repository import Database, Repository
from src.commerce_service.service import Service
from src.commerce_service.security import verify_api_key

app = FastAPI(title="Commerce Service API")

db = Database(":memory:")
db.init_db()
repository = Repository(db)
service = Service(repository)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_sku(sku_data: SKUCreate, api_key: str = Depends(verify_api_key)):
    return service.create_sku(sku_data.sku, sku_data.initial_stock)


@app.post("/stock/adjust", response_model=StockAdjustmentResponse)
def adjust_stock(data: StockAdjustment, api_key: str = Depends(verify_api_key)):
    return service.adjust_stock(data.sku, data.amount)


@app.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    res_data: ReservationCreate, api_key: str = Depends(verify_api_key)
):
    return service.create_reservation(res_data.sku, res_data.quantity, res_data.idempotency_key)


@app.post("/reservations/{reservation_id}/confirm", response_model=OrderResponse)
def confirm_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    return service.confirm_reservation(reservation_id)


@app.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(reservation_id: int, api_key: str = Depends(verify_api_key)):
    return service.cancel_reservation(reservation_id)


@app.get("/orders", response_model=OrderListResponse)
def list_orders(page: int = 1, size: int = 10):
    return service.list_orders(page, size)
