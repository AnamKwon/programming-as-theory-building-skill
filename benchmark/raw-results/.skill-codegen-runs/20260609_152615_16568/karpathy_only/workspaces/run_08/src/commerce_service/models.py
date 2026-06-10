from enum import Enum
from datetime import datetime
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
    sku: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    sku: str
    name: str
    stock: int
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    delta: int = Field(...)


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)
    ttl_seconds: int = Field(default=300, ge=60)


class ReservationResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime


class ReservationConfirmRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku: str
    quantity: int
    state: OrderState
    created_at: datetime
    confirmed_at: datetime | None


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
