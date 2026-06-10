from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    DRAFT = "draft"
    COMPLETED = "completed"


class SKU(BaseModel):
    id: int
    name: str
    quantity: int

    class Config:
        from_attributes = True


class SKUCreate(BaseModel):
    name: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=0)


class StockAdjustment(BaseModel):
    adjustment: int


class Reservation(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime
    idempotency_key: str

    class Config:
        from_attributes = True


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    expires_in_seconds: int = Field(default=3600, ge=60)
    idempotency_key: str = Field(..., min_length=1)


class OrderItem(BaseModel):
    reservation_id: int
    sku_id: int
    quantity: int

    class Config:
        from_attributes = True


class Order(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime
    items: list[OrderItem]

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    orders: list[Order]
    total: int
    skip: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
