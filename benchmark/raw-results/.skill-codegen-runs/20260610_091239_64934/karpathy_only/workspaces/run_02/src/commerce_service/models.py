"""Pydantic models for request/response validation."""

from decimal import Decimal
from datetime import datetime
from enum import Enum

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


class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    unit_price: Decimal = Field(..., gt=0, decimal_places=2)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    unit_price: Decimal
    stock_quantity: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    quantity_delta: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class CancelReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class HealthResponse(BaseModel):
    status: str
    version: str


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
