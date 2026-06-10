"""Data models for the commerce service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SKURequest(BaseModel):
    """Request to create a new SKU."""

    sku_id: str = Field(..., min_length=1, max_length=100)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    """Response containing SKU details."""

    sku_id: str
    stock: int
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    """Request to adjust stock for a SKU."""

    delta: int = Field(..., ne=0)


class ReservationRequest(BaseModel):
    """Request to create a reservation."""

    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    """Response containing reservation details."""

    reservation_id: str
    sku_id: str
    quantity: int
    status: Literal["pending", "confirmed", "cancelled"]
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    """Response containing order details."""

    order_id: str
    sku_id: str
    quantity: int
    status: Literal["pending", "completed", "cancelled"]
    created_at: datetime
    completed_at: datetime | None


class OrderListResponse(BaseModel):
    """Paginated list of orders."""

    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None
