"""Data models for inventory and orders."""

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
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKURequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    quantity: int = Field(...)
    reason: Optional[str] = Field(None, max_length=255)


class ReservationCreateRequest(BaseModel):
    order_id: int
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    expires_in_seconds: int = Field(default=3600, ge=60, le=86400)


class ReservationResponse(BaseModel):
    id: int
    order_id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    reservation_id: int
    sku_id: int
    quantity: int
    status: ReservationStatus


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime
    items: list[OrderItemResponse]

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int
