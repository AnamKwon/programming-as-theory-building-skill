from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    CREATED = "created"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class HealthResponse(BaseModel):
    status: str = Field(default="ok")


class SKURequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=100)
    stock_qty: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    stock_qty: int


class StockAdjustmentRequest(BaseModel):
    adjustment: int = Field(..., description="Positive or negative adjustment")


class StockAdjustmentResponse(BaseModel):
    id: int
    sku_code: str
    stock_qty: int


class ReservationRequest(BaseModel):
    sku_code: str = Field(..., min_length=1)
    qty: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku_code: str
    qty: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class ReservationConfirmRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    id: int
    sku_code: str
    qty: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int
