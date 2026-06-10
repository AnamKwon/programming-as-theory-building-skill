from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class SKURequest(BaseModel):
    sku: str
    initial_stock: int


class StockAdjustmentRequest(BaseModel):
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
    created_at: str
    updated_at: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class PaginatedOrders(BaseModel):
    page: int
    size: int
    total: int
    items: list[OrderResponse]


class StockResponse(BaseModel):
    sku: str
    available_stock: int
    total_stock: int
