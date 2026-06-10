"""Pydantic models for API requests and responses."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    """Order status values."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKUCreate(BaseModel):
    """Request to create a SKU."""
    sku_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


class SKUResponse(BaseModel):
    """SKU response."""
    id: int
    sku_code: str
    name: str
    created_at: datetime


class StockAdjustment(BaseModel):
    """Request to adjust stock level."""
    sku_code: str = Field(..., min_length=1)
    delta: int = Field(..., description="Positive or negative adjustment")


class ReservationCreate(BaseModel):
    """Request to create a reservation."""
    sku_code: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0, le=10000)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    """Reservation response."""
    id: int
    sku_code: str
    quantity: int
    status: str
    expires_at: datetime
    created_at: datetime


class OrderItemResponse(BaseModel):
    """Order item within an order."""
    sku_code: str
    quantity: int


class OrderResponse(BaseModel):
    """Order response with items."""
    id: int
    status: OrderStatus
    items: list[OrderItemResponse]
    created_at: datetime


class OrderListResponse(BaseModel):
    """Paginated order list."""
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
