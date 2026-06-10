from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CANCELLED = "cancelled"


class CreateSkuRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    total_stock: int = Field(..., gt=0)


class SkuResponse(BaseModel):
    id: int
    name: str
    total_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    adjustment: int

    @field_validator('adjustment')
    def adjustment_not_zero(cls, v):
        if v == 0:
            raise ValueError('adjustment must not be zero')
        return v


class CreateReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
