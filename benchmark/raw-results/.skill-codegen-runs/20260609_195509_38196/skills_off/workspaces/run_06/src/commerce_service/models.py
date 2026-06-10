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
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class SKUCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str
    current_stock: int


class StockAdjustment(BaseModel):
    quantity: int = Field(..., description="Positive to add, negative to subtract")


class ReservationCreate(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, ge=1, le=86400)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    created_at: datetime
    expires_at: datetime
    confirmed_at: Optional[datetime] = None


class ReservationActionResponse(BaseModel):
    reservation_id: int
    order_id: Optional[int] = None
    status: ReservationStatus
    message: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
