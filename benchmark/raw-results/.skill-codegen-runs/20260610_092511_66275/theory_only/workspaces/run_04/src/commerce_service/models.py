from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class SKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    available_stock: int
    reserved_stock: int
    total_stock: int


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(..., ne=0)


class ReservationRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=100)
    sku_id: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    reservation_id: str
    customer_id: str
    sku_id: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    customer_id: str
    sku_id: str
    quantity: int
    state: OrderState
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int
