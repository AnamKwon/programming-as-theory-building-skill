"""Data models for the commerce service."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, PositiveInt


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)


class SKUResponse(SKUCreate):
    id: int


class StockAdjustment(BaseModel):
    quantity: int = Field(..., ge=-1000000, le=1000000)


class ReservationCreate(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: PositiveInt
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime


class ReservationConfirm(BaseModel):
    pass


class ReservationCancel(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
