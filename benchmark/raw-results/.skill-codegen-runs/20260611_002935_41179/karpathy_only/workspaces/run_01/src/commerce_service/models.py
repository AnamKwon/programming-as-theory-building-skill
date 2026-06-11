"""Pydantic models for API requests and responses."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    """Request to create a new SKU."""
    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class AdjustStockRequest(BaseModel):
    """Request to adjust stock levels."""
    sku: str = Field(..., min_length=1)
    amount: int


class CreateReservationRequest(BaseModel):
    """Request to create a reservation."""
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    """Response model for a reservation."""
    id: int
    sku: str
    quantity: int
    status: str
    created_at: str
    updated_at: str


class OrderResponse(BaseModel):
    """Response model for an order."""
    id: int
    reservation_id: int
    created_at: str


class StockResponse(BaseModel):
    """Response model for stock adjustment."""
    sku: str
    available_stock: int


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str


class OrderListResponse(BaseModel):
    """Response model for order list."""
    orders: list[OrderResponse]
    page: int
    size: int
    total: int
