"""Data models for the commerce service."""

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
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"


# Request/Response Models

class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    price: float
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    quantity_delta: int = Field(..., description="Positive to add, negative to remove")


class ReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    reservation_id: Optional[str] = None

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    version: str


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
