from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    name: str
    available_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    sku: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime


class PaginatedOrdersResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    skip: int
    limit: int


class HealthResponse(BaseModel):
    status: str
    version: str
