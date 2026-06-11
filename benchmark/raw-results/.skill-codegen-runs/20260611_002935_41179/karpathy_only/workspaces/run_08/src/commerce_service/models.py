from datetime import datetime
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class StockAdjust(BaseModel):
    sku: str
    amount: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    idempotency_key: str
    status: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
