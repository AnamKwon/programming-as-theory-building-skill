"""Request and response models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# SKU endpoints
class CreateSKURequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    quantity: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    name: str
    quantity: int


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., description="Positive or negative adjustment")


# Reservation endpoints
class CreateReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


# Order endpoints
class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


# Generic responses
class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str = "ok"
