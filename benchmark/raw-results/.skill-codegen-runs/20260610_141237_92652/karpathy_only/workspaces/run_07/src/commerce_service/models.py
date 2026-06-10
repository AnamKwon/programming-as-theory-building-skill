"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    """Request model for creating a SKU."""

    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    """Response model for SKU."""

    sku: str
    stock: int


class StockAdjustment(BaseModel):
    """Request model for adjusting stock."""

    sku: str = Field(..., min_length=1)
    amount: int


class ReservationCreate(BaseModel):
    """Request model for creating a reservation."""

    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    """Response model for reservation."""

    id: int
    sku: str
    quantity: int
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    created_at: datetime
    idempotency_key: str


class OrderResponse(BaseModel):
    """Response model for order."""

    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    """Response model for paginated orders list."""

    orders: list[OrderResponse]
    page: int
    size: int
    total: int
