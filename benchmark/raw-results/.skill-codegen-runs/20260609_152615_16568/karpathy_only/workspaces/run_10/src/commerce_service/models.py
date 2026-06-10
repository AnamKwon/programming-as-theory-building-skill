"""Data models for commerce service."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SKU(BaseModel):
    """Stock Keeping Unit."""

    id: str
    quantity: int


class Reservation(BaseModel):
    """Inventory reservation."""

    id: str
    sku_id: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: datetime
    idempotency_key: str


class Order(BaseModel):
    """Confirmed order."""

    id: str
    sku_id: str
    quantity: int
    reservation_id: str
    created_at: datetime


# Request/Response models


class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=0)


class CreateSKUResponse(BaseModel):
    sku_id: str
    quantity: int


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(..., description="Positive or negative adjustment")


class AdjustStockResponse(BaseModel):
    sku_id: str
    quantity: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class CreateReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    state: ReservationState
    expires_at: datetime


class ConfirmReservationResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    state: str


class CancelReservationResponse(BaseModel):
    reservation_id: str
    state: ReservationState


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    reservation_id: str
    created_at: datetime


class OrderListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[OrderResponse]


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
