from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1)


class StockAdjustment(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=-999999, lt=999999)


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class ReservationResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    state: OrderState
    created_at: datetime


class OrdersPage(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
