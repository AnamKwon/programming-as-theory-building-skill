from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    name: str
    stock: int
    reserved: int

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(..., description="Positive or negative adjustment")


class CreateReservationRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=100)
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    order_id: str
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    order_id: str
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True
