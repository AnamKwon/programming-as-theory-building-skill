"""Domain models and Pydantic schemas."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderState(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"


class SKUSchema(BaseModel):
    sku: str
    name: str


class SKUResponse(SKUSchema):
    id: int
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    adjustment: int = Field(..., description="Quantity to add (positive) or remove (negative)")


class ReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku_id: str
    quantity: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    state: OrderState
    created_at: datetime


class PaginatedOrderResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ErrorResponse(BaseModel):
    detail: str
