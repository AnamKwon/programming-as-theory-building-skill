"""Pydantic models for request/response validation."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SKURequest(BaseModel):
    """Request to create a new SKU."""
    sku: str
    initial_stock: int = Field(gt=0)


class SKUResponse(BaseModel):
    """SKU details response."""
    id: int
    sku: str
    available_stock: int


class StockAdjustRequest(BaseModel):
    """Request to adjust stock levels."""
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    """Response after stock adjustment."""
    sku: str
    available_stock: int


class ReservationRequest(BaseModel):
    """Request to create a reservation."""
    sku: str
    quantity: int = Field(gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    """Reservation details response."""
    id: int
    sku: str
    quantity: int
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    idempotency_key: str
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    """Response after confirming a reservation."""
    id: int
    status: Literal["CONFIRMED", "EXPIRED"]
    order_id: int | None


class CancelReservationResponse(BaseModel):
    """Response after cancelling a reservation."""
    id: int
    status: Literal["CANCELLED"]
    stock_restored: int


class OrderResponse(BaseModel):
    """Order details response."""
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    """Paginated list of orders."""
    orders: list[OrderResponse]
    page: int
    size: int
    total: int
