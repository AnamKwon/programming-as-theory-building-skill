"""Data models for Pydantic validation and database entities."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SKURequest(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    product_name: str
    available_stock: int
    reserved_stock: int


class StockAdjustmentRequest(BaseModel):
    quantity_change: int = Field(..., description="Positive to add, negative to subtract")


class ReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    next_cursor: Optional[int] = None


class ErrorResponse(BaseModel):
    detail: str


class SKU:
    """Database entity for a SKU."""

    def __init__(
        self,
        id: int,
        product_name: str,
        available_stock: int,
        reserved_stock: int,
    ):
        self.id = id
        self.product_name = product_name
        self.available_stock = available_stock
        self.reserved_stock = reserved_stock


class Reservation:
    """Database entity for a reservation."""

    def __init__(
        self,
        id: int,
        sku_id: int,
        quantity: int,
        status: ReservationStatus,
        idempotency_key: str,
        expires_at: datetime,
        created_at: datetime,
    ):
        self.id = id
        self.sku_id = sku_id
        self.quantity = quantity
        self.status = status
        self.idempotency_key = idempotency_key
        self.expires_at = expires_at
        self.created_at = created_at


class Order:
    """Database entity for an order (confirmed reservation)."""

    def __init__(
        self,
        id: int,
        reservation_id: int,
        sku_id: int,
        quantity: int,
        status: ReservationStatus,
        created_at: datetime,
    ):
        self.id = id
        self.reservation_id = reservation_id
        self.sku_id = sku_id
        self.quantity = quantity
        self.status = status
        self.created_at = created_at
