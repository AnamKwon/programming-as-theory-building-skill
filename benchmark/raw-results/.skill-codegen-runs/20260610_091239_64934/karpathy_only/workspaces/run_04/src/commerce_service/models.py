from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ReservationStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CreateSKURequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class AdjustStockRequest(BaseModel):
    quantity: int


class CreateReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    stock: int


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    status: str
    created_at: datetime
    reservations: list[ReservationResponse]


class OrderListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    orders: list[OrderResponse]
