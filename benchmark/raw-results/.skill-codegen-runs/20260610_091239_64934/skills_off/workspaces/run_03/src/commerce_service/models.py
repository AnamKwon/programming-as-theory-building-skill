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
    name: str = Field(..., min_length=1, max_length=200)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str
    current_stock: int
    reserved_stock: int


class StockAdjustment(BaseModel):
    quantity: int = Field(..., ge=-1000000, le=1000000)


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    reservation_id: Optional[int]
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
