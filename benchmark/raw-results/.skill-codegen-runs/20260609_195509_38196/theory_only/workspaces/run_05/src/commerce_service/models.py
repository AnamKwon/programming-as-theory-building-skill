from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"


class HealthResponse(BaseModel):
    status: str = "healthy"


class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=500)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    stock: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., description="Positive or negative stock adjustment")


class StockResponse(BaseModel):
    sku_id: str
    stock: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class CancelReservationRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class CreateOrderRequest(BaseModel):
    reservation_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    state: OrderState
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
