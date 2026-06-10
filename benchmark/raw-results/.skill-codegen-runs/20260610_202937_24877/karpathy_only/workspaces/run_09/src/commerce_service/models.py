from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int
    created_at: datetime


class StockAdjustRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    previous_stock: int
    adjusted_amount: int
    new_stock: int


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    page: int
    size: int
    total: int
    orders: list[OrderResponse]


class HealthResponse(BaseModel):
    status: str
