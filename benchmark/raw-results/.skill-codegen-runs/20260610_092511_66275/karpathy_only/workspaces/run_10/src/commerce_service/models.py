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
    CANCELLED = "cancelled"


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    quantity: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    description: str
    quantity: int


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(..., description="Positive or negative adjustment")


class CreateReservationRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=100)
    sku: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=200)


class ReservationResponse(BaseModel):
    reservation_id: str
    order_id: str
    sku: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class CancelReservationRequest(BaseModel):
    pass


class OrderItemResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    status: ReservationStatus


class OrderResponse(BaseModel):
    order_id: str
    status: OrderStatus
    items: list[OrderItemResponse]
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
