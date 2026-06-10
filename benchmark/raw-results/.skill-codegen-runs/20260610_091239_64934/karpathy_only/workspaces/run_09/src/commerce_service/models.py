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


class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    stock_quantity: int


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(..., ne=0)


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class ReservationConfirm(BaseModel):
    pass


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
