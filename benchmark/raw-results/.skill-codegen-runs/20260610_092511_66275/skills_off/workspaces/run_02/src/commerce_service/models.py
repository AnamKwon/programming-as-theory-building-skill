from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    sku: str
    name: str


class StockAdjustmentRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=-1000000, le=1000000)


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=1, le=1000000)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    state: OrderState
    created_at: datetime


class OrdersListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    skip: int
    limit: int
