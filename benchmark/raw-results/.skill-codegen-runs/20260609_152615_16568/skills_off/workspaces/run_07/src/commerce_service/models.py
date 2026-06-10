from datetime import datetime, timedelta
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


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


class SKUResponse(BaseModel):
    id: int
    sku: str
    name: str


class StockAdjustmentRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=-1000000, lt=1000000)


class ReservationCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0, le=1000000)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    customer_id: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: ReservationStatus
    customer_id: str
    created_at: str
    expires_at: str
    order_id: Optional[int] = None


class ReservationActionRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    customer_id: str
    created_at: str
    updated_at: str
    items: list[dict] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    timestamp: str
