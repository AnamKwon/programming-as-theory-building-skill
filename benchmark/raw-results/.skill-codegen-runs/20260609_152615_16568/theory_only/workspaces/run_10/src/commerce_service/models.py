"""Pydantic models for request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class SKURequest(BaseModel):
    sku_code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    stock_count: int

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(..., description="Positive to add, negative to subtract")


class ReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    order_id: Optional[int] = None

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
