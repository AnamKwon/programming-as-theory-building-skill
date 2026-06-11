"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int


class AdjustStockRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    amount: int


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: ReservationStatus
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class CancelReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrdersListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
