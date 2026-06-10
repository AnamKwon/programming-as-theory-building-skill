from enum import Enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Request/Response Models

class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    current_stock: int
    reserved_stock: int
    available_stock: int


class AdjustStockRequest(BaseModel):
    delta: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    status: OrderStatus
    created_at: datetime
    reservations: list[ReservationResponse]


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int


class HealthResponse(BaseModel):
    status: str = "ok"
