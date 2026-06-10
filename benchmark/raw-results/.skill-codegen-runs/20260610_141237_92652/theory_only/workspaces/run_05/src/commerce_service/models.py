from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    available_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class AdjustStockResponse(BaseModel):
    sku: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: str
    idempotency_key: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class OrderListResponse(BaseModel):
    page: int
    size: int
    total: int
    orders: list[OrderResponse]


class HealthResponse(BaseModel):
    status: str
