from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SkuRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., ge=0)


class SkuResponse(BaseModel):
    id: int
    name: str
    quantity_available: int


class StockAdjustmentRequest(BaseModel):
    quantity_delta: int = Field(...)


class ReservationRequest(BaseModel):
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


class ConfirmReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    size: int
