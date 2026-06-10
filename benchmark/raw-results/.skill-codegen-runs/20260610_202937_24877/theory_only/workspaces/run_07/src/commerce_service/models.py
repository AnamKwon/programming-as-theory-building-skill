from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class StockAdjustmentRequest(BaseModel):
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
    idempotency_key: str
    status: str
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    page: int
    size: int
    total: int
    items: list[OrderResponse]


class StockAdjustmentResponse(BaseModel):
    sku: str
    available_stock: int


class HealthResponse(BaseModel):
    status: str
