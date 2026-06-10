from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    total_stock: int = Field(..., gt=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    total_stock: int
    available_stock: int
    reserved_stock: int
    created_at: datetime


class StockAdjustment(BaseModel):
    quantity_change: int


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime
    confirmed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class OrderResponse(BaseModel):
    order_id: str
    reservation_ids: list[str]
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
