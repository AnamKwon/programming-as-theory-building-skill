"""Domain models and request/response schemas."""

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
    PLACED = "placed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


# Request schemas
class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)


class AdjustStockRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    adjustment: int = Field(..., ge=-1000, le=1000)


class CreateReservationRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=50)
    sku_id: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=1, le=10000)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ConfirmReservationRequest(BaseModel):
    reservation_id: str = Field(..., min_length=1)


class CancelReservationRequest(BaseModel):
    reservation_id: str = Field(..., min_length=1)


class PaginationParams(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=100)


# Response schemas
class SKUResponse(BaseModel):
    sku_id: str
    name: str


class StockLevelResponse(BaseModel):
    sku_id: str
    available: int
    reserved: int


class ReservationResponse(BaseModel):
    id: str
    order_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: Optional[datetime]


class OrderResponse(BaseModel):
    id: str
    status: OrderStatus
    created_at: datetime


class OrderDetailResponse(BaseModel):
    order: OrderResponse
    reservations: list[ReservationResponse]


class HealthResponse(BaseModel):
    status: str
    version: str
