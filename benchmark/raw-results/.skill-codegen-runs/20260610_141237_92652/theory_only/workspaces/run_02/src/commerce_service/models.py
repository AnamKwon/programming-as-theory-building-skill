from pydantic import BaseModel
from datetime import datetime


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int
    total_stock: int
    created_at: datetime


class StockAdjust(BaseModel):
    sku: str
    amount: int


class ReservationCreate(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    idempotency_key: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class HealthResponse(BaseModel):
    status: str


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    size: int
