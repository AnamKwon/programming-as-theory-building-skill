from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
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
    idempotency_key: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class HealthResponse(BaseModel):
    status: str
