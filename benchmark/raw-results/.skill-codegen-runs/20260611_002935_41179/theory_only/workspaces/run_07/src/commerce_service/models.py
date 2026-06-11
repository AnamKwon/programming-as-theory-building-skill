from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CreateSkuRequest(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
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
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class SkuResponse(BaseModel):
    sku: str
    stock: int


class AdjustStockResponse(BaseModel):
    sku: str
    stock: int
