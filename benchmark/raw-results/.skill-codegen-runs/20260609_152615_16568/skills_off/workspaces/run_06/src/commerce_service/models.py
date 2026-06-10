"""Pydantic models for request/response validation."""

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


class HealthResponse(BaseModel):
    status: str = "healthy"


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    stock_qty: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    stock_qty: int
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    delta: int = Field(..., description="Quantity delta (positive or negative)")


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    qty: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    qty: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku: str
    qty: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
