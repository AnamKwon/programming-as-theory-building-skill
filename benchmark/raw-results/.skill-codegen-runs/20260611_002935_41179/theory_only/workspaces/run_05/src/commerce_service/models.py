from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int
    created_at: datetime
    updated_at: datetime


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class StockResponse(BaseModel):
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
    idempotency_key: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
