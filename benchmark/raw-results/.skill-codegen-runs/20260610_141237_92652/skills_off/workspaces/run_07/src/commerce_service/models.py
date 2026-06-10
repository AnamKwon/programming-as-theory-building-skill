"""Pydantic models and database schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    """Request to create a new SKU."""

    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    """Request to adjust stock level."""

    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    """Request to create a reservation."""

    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    """Response with reservation details."""

    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime


class OrderResponse(BaseModel):
    """Response with order details."""

    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    """Paginated list of orders."""

    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
